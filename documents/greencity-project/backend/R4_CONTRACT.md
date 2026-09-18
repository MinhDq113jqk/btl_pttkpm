# R4 — nền tảng billing, công nợ và thanh toán

## Phạm vi và trạng thái

Revision `0010` kế thừa `0009`. Task 4 tích hợp lát cắt nhận payment thủ công,
match payment thiếu mã, phân bổ oldest-debt-first và Overpayment Credit cơ bản;
không mở refund, Deposit/Restricted Fund hay maker-checker. `invoice_items` R2
vẫn là posting anchor cũ; Invoice Item R4 là bảng riêng `billing_invoice_items`.

Mọi aggregate R4 lưu `tenant_id`, `site_id`, `building_id`. Composite foreign
key buộc site thuộc tenant, building thuộc site, Billing Account thuộc Unit cùng
building, và các quan hệ Billing Run/Invoice/Payment/Allocation/Credit/Ledger
không thể nhảy sang building khác. API lấy tenant/site/building từ
`UserContext`; payload không có trường nới scope.

Các bảng chính:

- `billing_accounts`, `billing_fee_policies`, `billing_fee_policy_versions`;
  version publish dùng `UNIT_AREA_M2`, `unit_rate_vnd` và `rounding_unit_vnd`
  đều là integer VND, có effective date và snapshot lúc phát hành.
- `accounting_periods`, `billing_runs`, `billing_invoices`,
  `billing_invoice_items`.
- `payments`, `payment_allocations`, `unmatched_payments`,
  `overpayment_credits`, `ar_ledger_entries`.

Toàn bộ số tiền VND dùng PostgreSQL `BIGINT`; request Payment dùng strict integer
và từ chối float, boolean và datetime không timezone.

## State machine

- Accounting Period public R4: `OPEN → CLOSING → CLOSED`, có thể hủy đóng từ
  `CLOSING → OPEN`. `CLOSED` là terminal trên API R4. `LOCKED` và reopen giới
  hạn `CLOSED → CLOSING` chỉ thuộc future maker-checker command, không được
  expose bởi R4.
- Billing Run: `DRAFT → CALCULATING → REVIEW → POSTED`; lỗi đi
  `CALCULATING → FAILED → CALCULATING` với cùng run key, giữ mã/lý do lỗi và
  số lần retry. `POSTED` terminal.
- Invoice: `DRAFT → ISSUED → PARTIALLY_PAID → PAID`; chỉ draft/issued có nhánh
  `VOID`; `PAID`/`VOID` terminal.
- Payment nhận có mã bắt đầu `RECEIVED`; `RECEIVED → ALLOCATING → ALLOCATED|
  OVERPAID`. Payment thiếu mã bắt đầu `UNMATCHED`, chỉ `UNMATCHED → RECEIVED`
  sau match hợp lệ rồi mới được allocation; `REVERSED` terminal.

Trigger DB `trg_payment_allocations_cap` lock Payment và Invoice trong một
transaction, buộc cùng Billing Account, Invoice còn mở và chỉ nhận số tiền
`<= min(payment_available, invoice_open_balance)`. Cap cũng xét tổng allocation
so với invoice total để direct DB insert không vượt dư nợ dù snapshot đã cập nhật.

## Idempotency và tính bất biến

- Billing Run có cả `site_id + run_key` và
  `building_id + accounting_period_id + fee_policy_version_id` unique.
- Payment có unique cả `(tenant_id, site_id, payment_source, source_reference)`
  và `(tenant_id, site_id, receipt_number)`. API dùng `idempotency_records`
  theo tenant/site/actor/operation/key cho receive, match và allocate. Hai actor
  dùng key khác nhau nhưng cùng source/receipt vẫn chỉ có một Payment thắng.
- Tab Billing giữ Idempotency-Key theo payload của intent cho tới khi nhận kết
  quả thành công. Nếu response bị mất sau khi server commit, người dùng retry
  không đổi payload sẽ nhận lại cùng resource thay vì tạo Payment thứ hai.
- `ar_ledger_entries` có debit hoặc credit dương duy nhất (không cả hai), unique
  source/type và trigger `trg_ar_ledger_entries_append_only` chặn `UPDATE`/
  `DELETE`. Audit trigger R2 `trg_audit_events_append_only` vẫn giữ nguyên.

Sửa hạch toán sai phải tạo bút toán `REVERSAL` mới. Không update/delete ledger.

## API foundation / OpenAPI

- `GET /api/v1/billing/accounts`, `GET /api/v1/billing/accounts/{id}`: chỉ
  `admin`/`director`/`accountant`; list và lookup bị lọc active site và building
  grant server-side. Ngoài scope trả `404 ERR-SCOPE-NOTFOUND`; thiếu role trả
  `403 ERR-FORBIDDEN`.
- `POST /api/v1/billing/payments`: cùng role, bắt buộc `Idempotency-Key`.
  Body nhận đúng một trong Billing Account hoặc building cho payment thiếu mã,
  Accounting Period, source/receipt, strict `amount_vnd` và `received_at`. Kỳ
  phải `OPEN`/`CLOSING`; account phải ACTIVE. Payment có mã tạo `RECEIVED` cùng
  `PAYMENT_RECEIVED` credit ledger; payment thiếu mã tạo `UNMATCHED` và
  `UnmatchedPayment OPEN` nhưng không tạo AR ledger hay giảm dư nợ. Source/receipt
  trùng trả `409 ERR-DUPLICATE-PAYMENT`; cùng idempotency key + payload replay
  cùng Payment.

Seed chỉ tạo Billing Account, Fee Policy/version và Accounting Period `OPEN` tối
thiểu cho mỗi site demo; không tạo invoice, payment, allocation, credit,
unmatched payment hoặc AR history giả.

## API Task 2 / OpenAPI

- `GET|POST /api/v1/billing/fee-policies` và
  `POST /api/v1/billing/fee-policies/{id}/versions`: policy/version scoped từ
  session, bắt buộc idempotency ở thao tác ghi. Version mới không được hồi tố
  vào kỳ `CLOSING` (`ERR-POLICY-EFFECTIVE-NEXT-PERIOD`).
- `GET|POST /api/v1/billing/periods`,
  `POST /api/v1/billing/periods/{id}/transition`: chỉ cho `OPEN → CLOSING →
  CLOSED`; request transition mang `expected_version`. Kỳ lưu `cutoff_at` có
  timezone.
- `GET|POST /api/v1/billing/runs`, `POST /api/v1/billing/runs/{id}/retry`:
  database unique `(building, period, policy version)` là hàng rào chống chạy
  trùng. Tính toàn bộ invoice/item/AR debit trong savepoint; lỗi không để lại
  hóa đơn partial và Run thành `FAILED` để retry cùng ID.
- `GET /api/v1/billing/invoices`, `GET /api/v1/billing/invoices/{id}`,
  `POST /api/v1/billing/invoices/{id}/void`: item snapshot bị DB chặn UPDATE/
  DELETE. Void chỉ hóa đơn `ISSUED`, chưa allocation, kỳ `OPEN`; tổng lịch sử
  giữ nguyên, dư nợ về 0 và append AR `REVERSAL` credit.

`ALG-01` ở Task 2 dùng `Unit.area_m2 × unit_rate_vnd`, `Decimal` và làm tròn
half-up đúng một lần theo `rounding_unit_vnd`. Pending Charge đã `APPROVED`
chỉ vào Run khi `reviewed_at <= cutoff_at`; sau cutoff tự được xét ở kỳ OPEN kế
tiếp, không chèn ngược vào snapshot cũ. Proration, tax, min/max và credit note
đầy đủ vẫn `SPEC-ONLY` cho lát cắt này.

## API Task 3 / OpenAPI

- `GET /api/v1/billing/payments`, `GET /api/v1/billing/unmatched-payments` và
  `GET /api/v1/billing/overpayment-credits` chỉ list trong active-site/building
  grant; CSKH nhận `403`, đối tượng ngoài scope không bị lộ.
- `POST /api/v1/billing/unmatched-payments/{id}/match` bắt buộc
  `Idempotency-Key`, lock unmatched/payment/account/period, chỉ match account
  ACTIVE cùng building, append `PAYMENT_RECEIVED` sau match và đánh dấu hàng đợi
  `RESOLVED` trong một transaction.
- `POST /api/v1/billing/payments/{id}/allocate` bắt buộc `Idempotency-Key`, lock
  Payment rồi các Invoice còn nợ cùng Billing Account, sort `due_on ASC →
  issued_on ASC → invoice_number ASC → id ASC`, tạo `PaymentAllocation`, cập nhật
  snapshot `outstanding_vnd`/status `PARTIALLY_PAID|PAID`. Khi còn dư, endpoint
  tạo đúng một `OverpaymentCredit OPEN` và append `CREDIT_ISSUED` debit; Credit
  không tự áp vào kỳ tương lai trong R4.
- Receive/match/allocate đều ghi audit và outbox. AR ledger/audit append-only;
  sửa sai cần bút toán mới, không update/delete snapshot history hay ledger.

## Task 4 — Golden Flow và oracle cố định

Acceptance test gọi API trên PostgreSQL cô lập với Unit `80,25 m²`, rate
`12.000 VND/m²`, rounding `1 VND`: mỗi Invoice có total `963.000 VND`. Payment
`1.000.000 VND` phân bổ tất định `963.000 + 37.000`, nên AR debt là `926.000`.
Receipt thiếu mã `100.000 VND` không tạo AR và không đổi debt; sau match cùng
building + allocation debt là `826.000`. Trong cả hai payment, `total_vnd` và
Invoice Item snapshot bằng đúng giá trị trước payment.

Nhánh lỗi dùng Unit `0 m²` để Run `FAILED` không để lại Invoice partial; sau
sửa Unit thành `82,58 m²`, retry cùng Run với rounding `1.000 VND` phát hành
Invoice `991.000 VND`. Replay receive/retry cùng key trả resource cũ; source
trùng với key khác bị từ chối. Đây là bằng chứng local cho AC-11..14,
AC-16..19, AC-30, AC-36 và AC-44. AC-15 vẫn `SPEC-ONLY`: acceptance test chỉ
khóa việc public API từ chối `CLOSED → LOCKED` và `CLOSED → CLOSING`, không
triển khai reopen/maker-checker. Refund, chargeback và automatic credit
application ngoài scope.

## Task 5 — ma trận AC và Evidence Exit R4

Ma trận này là truy vết evidence local, không thay thế acceptance thủ công hay
verdict review độc lập. `scripts.test_isolated` tạo một PostgreSQL/TLS disposable
cluster, kiểm migration/seed/drift rồi chạy các test bên dưới; không dùng Aiven
hoặc database vận hành.

Chạy từ thư mục `backend/`:

```powershell
.\.venv\Scripts\python.exe -m scripts.test_isolated --pg-bin 'C:\Program Files\PostgreSQL\18\bin' --openssl 'C:\Program Files\Git\usr\bin\openssl.exe'
```

| Mục | Evidence tự động chính | Kết quả phải giữ |
|---|---|---|
| AC-11 | `test_r4_money_oracles_are_integer_vnd_and_round_once_half_up`; `test_r4_golden_flow_policy_period_run_issues_immutable_snapshot_and_ledger` | Oracle `963.000 VND`, rounding half-up đúng một lần, snapshot Item bất biến |
| AC-12 | `test_r4_two_concurrent_accountants_have_one_billing_run_winner` | Hai connection chỉ có một Billing Run/Invoice thắng; request kia `ERR-RUN-DUPLICATE` |
| AC-13 | `test_r4_run_failure_is_atomic_and_retry_reuses_the_same_run`; Golden Flow retry | Lỗi không để Invoice partial; retry cùng Run tạo đúng tập invoice |
| AC-14 | `test_r4_charge_after_cutoff_moves_to_next_period` | Charge sau cutoff chỉ xuất hiện ở kỳ OPEN kế tiếp |
| AC-15 (`SPEC-ONLY`) | `test_r4_public_period_transition_rejects_future_only_commands` | API từ chối `CLOSED → LOCKED` và reopen; không coi là triển khai maker-checker/limited reopen |
| AC-16 | `test_r4_void_requires_open_unallocated_invoice_and_preserves_history`; `test_r4_void_rejects_allocated_invoice_and_closed_period` | Void chỉ invoice chưa allocation/kỳ OPEN; lịch sử là reversal append-only |
| AC-17 | `test_ac17_ac44_auto_allocates_oldest_debt_partial_and_multi_invoice` | Allocation oldest-debt-first, partial/multi-invoice và cap ở DB |
| AC-18 | `test_ac18_unmatched_does_not_reduce_debt_until_scoped_match_then_allocation` | Unmatched không có AR/không giảm debt cho tới match hợp lệ |
| AC-19 (basic R4) | `test_ac19_excess_is_a_separate_overpayment_credit_not_an_invoice_or_deposit` | Phần dư chỉ tạo Overpayment Credit, không Deposit/Restricted Fund |
| AC-30 | `test_ac30_two_accountants_with_different_idempotency_keys_create_one_payment` | Source/receipt race chỉ tạo một Payment |
| AC-36 (supporting regression) | `greencity-app/tests/payment-ux.cjs` | Retry sau response mất giữ Idempotency-Key và không tạo Payment thứ hai |
| AC-44 | `test_r4_fixed_oracle_financial_golden_flow_with_idempotent_recovery` | Fee policy → invoice → payment/match/allocation, debt và snapshot khớp oracle |

Các control xuyên suốt được giữ bằng
`test_r4_scope_hides_billing_accounts_outside_tenant_site_or_building`
(tenant/site/building đều `404 ERR-SCOPE-NOTFOUND`),
`test_r4_payment_deduplicates_source_and_receipt_and_writes_immutable_ledger_and_audit`
(audit/AR ledger chặn `UPDATE` và `DELETE`) và
`test_production_app_has_no_test_probes` (OpenAPI path contract).
Seed idempotent chỉ tạo setup R4 tối thiểu; không tạo debt, invoice hoặc payment
giả để kết quả acceptance không bị che khuất.

### Ranh giới Exit R4

Theo release row, Exit R4 local gồm AC-11..14, AC-16..18, AC-30 và AC-44. Basic
AC-19 và AC-36 được regression thêm; AC-15, refund/chargeback, proration nâng
cao, automatic credit application và maker-checker vẫn ngoài scope. Chỉ khi
migration runner, regression cô lập, frontend regression/build và review độc lập
có evidence riêng mới được xem xét Gate/production.
