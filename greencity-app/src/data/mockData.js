export const currentUser = {
  name: "Nguyễn Giám Đốc",
  role: "Giám đốc BQL",
  avatarText: "KT",
  status: "online",
  currentSite: "GreenCity Central",
  availableSites: ["GreenCity Central", "GreenCity Riverside", "GreenCity SkyVilla"]
};

export const navItems = [
  { id: "overview", label: "Tổng quan", icon: "LayoutDashboard", count: null },
  { id: "refund-form", label: "Phiếu hoàn tiền & Hoá đơn", icon: "Receipt", count: 3, isForm: true },
  { id: "tasks", label: "Công việc & Yêu cầu", icon: "CheckSquare", count: 12 },
  { id: "projects", label: "Dự án & Mặt bằng", icon: "Building2", count: null },
  { id: "amenities", label: "Tiện ích & Thương mại", icon: "Store", count: "Mới" },
  { id: "technical", label: "Kỹ thuật & Bảo trì", icon: "Wrench", count: null },
  { id: "cleaning", label: "Vệ sinh môi trường", icon: "Sparkles", count: null },
  { id: "security", label: "An ninh & Tuần tra", icon: "ShieldCheck", count: null },
  { id: "residents", label: "Khách hàng & Cư dân", icon: "Users", count: null },
  { id: "finance", label: "Tài chính & Công nợ", icon: "BadgePercent", count: null },
  { id: "media", label: "Website & Fanpage", icon: "Globe", count: "Live" },
  { id: "reports", label: "Báo cáo điều hành", icon: "BarChart3", count: null },
  { id: "notifications", label: "Thông báo", icon: "Bell", count: 4 },
  { id: "settings", label: "Quản trị hệ thống", icon: "Settings", count: null }
];

export const dashboardData = {
  greeting: "Chào buổi sáng, Giám đốc",
  summaryNotice: "Có 12 hồ sơ đang chờ phê duyệt và 4 công việc cần xử lý trước cuối ngày.",
  weeklyProgress: 82,
  onTimeRate: 91,
  kpis: [
    {
      id: "in_progress",
      label: "Việc đang xử lý",
      value: "38",
      subtext: "+6 trong hôm nay",
      type: "blue",
      icon: "Briefcase"
    },
    {
      id: "pending_approval",
      label: "Chờ phê duyệt",
      value: "12",
      subtext: "4 việc ưu tiên",
      type: "amber",
      icon: "Clock"
    },
    {
      id: "completed_month",
      label: "Hoàn thành tháng",
      value: "146",
      subtext: "+18,4% so tháng trước",
      type: "emerald",
      icon: "CheckCircle2"
    },
    {
      id: "active_staff",
      label: "Nhân sự hoạt động",
      value: "42",
      subtext: "6 đội / 3 công trình",
      type: "purple",
      icon: "Users"
    }
  ],
  urgentTasks: [
    {
      id: "KT-2608-118",
      title: "Kiểm tra hệ thống chiếu sáng khu A",
      location: "Grand Park A · Khuôn viên",
      status: "Đang xử lý",
      statusColor: "blue",
      deadline: "Hôm nay, 16:30"
    },
    {
      id: "KT-2608-103",
      title: "Nghiệm thu bảo trì thang máy tòa A",
      location: "Grand Park A · Sảnh tầng 1",
      status: "Chờ duyệt",
      statusColor: "amber",
      deadline: "Ngày mai, 09:00"
    },
    {
      id: "KT-2608-097",
      title: "Bổ sung ảnh kiểm tra hệ thống điện",
      location: "Grand Park B · Phòng kỹ thuật",
      status: "Quá hạn",
      statusColor: "rose",
      deadline: "Trễ 1 ngày"
    },
    {
      id: "TC-2608-016",
      title: "Hồ sơ hoàn phí thừa căn A101 - Grand Park",
      location: "GreenCity Central",
      status: "Chờ duyệt",
      statusColor: "amber",
      deadline: "Hôm nay, 17:00",
      actionForm: true
    }
  ],
  operationsStatus: [
    { label: "Công việc đúng hạn", percentage: 91, color: "bg-emerald-500" },
    { label: "Báo cáo đã nộp", percentage: 76, color: "bg-blue-500" },
    { label: "Hồ sơ đã duyệt", percentage: 68, color: "bg-amber-500" }
  ],
  alertBox: {
    count: 4,
    text: "4 việc cần can thiệp",
    detail: "Quá hạn hoặc đang bị vướng tại 2 công trình."
  }
};

export const sampleRefundCase = {
  caseCode: "RFD-20260907-0016",
  status: "Chờ xử lý",
  resident: {
    name: "Trần Thị Mai",
    unitCode: "A101",
    building: "Tòa Grand Park A",
    projectName: "GreenCity Urban Central",
    phone: "0912-345-678",
    email: "mai.tran@greencity.vn",
    contractPeriod: "2026/01/01 ~ 2026/12/31",
    liabilityEpisodeId: "LEP-A101-2026",
    verifiedResident: true
  },
  reason: {
    type: "Thu thừa phí quản lý vận hành (Overpayment Credit)",
    sourceDocument: "Hóa đơn kỳ 08/2026 (INV-202608-0128)",
    approver: "Giám đốc Ban Quản Lý",
    createdDate: "2026/09/02",
    description: "Căn A101 thanh toán 2 lần chuyển khoản cho kỳ 08/2026. Số dư thừa 3.000.000 đ được duyệt hoàn trả theo quy định tài chính."
  },
  financials: {
    originalAmount: 3000000,
    alreadyRefunded: 0,
    remainingAmount: 3000000,
    currentRefundAmount: 3000000,
    postingDate: "2026/09/04"
  },
  beneficiaryAccount: {
    method: "bank_transfer",
    bankName: "Ngân hàng TMCP Ngoại thương VN (Vietcombank)",
    branchName: "Chi nhánh Ba Đình - Hà Nội",
    accountHolder: "TRẦN THỊ MAI",
    accountNumber: "1023456789012",
    isMatchedWithResident: true
  },
  attachments: [
    {
      id: "att-1",
      name: "sao_ke_chuyen_khoan_trung_A101.pdf",
      size: "1.8 MB",
      uploadTime: "02/09/2026 14:20",
      type: "pdf"
    },
    {
      id: "att-2",
      name: "don_de_nghi_hoan_tien_chu_ho.png",
      size: "2.4 MB",
      uploadTime: "02/09/2026 14:22",
      type: "image"
    }
  ]
};

export const mediaData = {
  facebook: {
    pageName: "GreenCity Urban - Khu Đô Thị Xanh Thông Minh",
    handle: "@greencity.official",
    followers: "48.520",
    rating: "4.9/5 (1.240 đánh giá)",
    verified: true,
    connectionStatus: "Chưa kết nối Meta · Dữ liệu mẫu",
    tokenExpiry: "Chưa có kết nối",
    unreadMessages: 6,
    reachThisMonth: "128.400",
    engagementRate: "8.4%",
    posts: [
      {
        id: "fb-1",
        title: "Thông báo bảo trì định kỳ hệ thống máy bơm nước tháp Grand Park A",
        date: "06/09/2026 10:00",
        reach: 4850,
        likes: 246,
        comments: 32,
        shares: 18,
        status: "Đã xuất bản",
        image: "https://images.unsplash.com/photo-1545324418-cc1a3fa10c00?auto=format&fit=crop&w=600&q=80"
      },
      {
        id: "fb-2",
        title: "Lễ hội Mùa thu 'GreenCity Eco-Festival 2026' dành riêng cho cư dân",
        date: "04/09/2026 15:30",
        reach: 12800,
        likes: 892,
        comments: 145,
        shares: 64,
        status: "Đã xuất bản",
        image: "https://images.unsplash.com/photo-1511578314322-379afb476865?auto=format&fit=crop&w=600&q=80"
      },
      {
        id: "fb-3",
        title: "Hướng dẫn kích hoạt tài khoản Cổng cư dân GreenCity phiên bản mới",
        date: "Lên lịch: 10/09/2026 09:00",
        reach: 0,
        likes: 0,
        comments: 0,
        shares: 0,
        status: "Đã lên lịch",
        image: "https://images.unsplash.com/photo-1551836022-d5d88e9218df?auto=format&fit=crop&w=600&q=80"
      }
    ],
    inbox: [
      {
        id: "msg-1",
        sender: "Nguyễn Hoàng Long",
        avatar: "NL",
        preview: "Chào ban quản lý, cho mình hỏi lịch đăng ký sử dụng sân pickleball cuối tuần này?",
        time: "15 phút trước",
        unread: true
      },
      {
        id: "msg-2",
        sender: "Phạm Thùy Linh (Căn B1204)",
        avatar: "PL",
        preview: "Mình vừa chuyển khoản tiền phí dịch vụ tháng 8, BQL kiểm tra giúp mình nhé.",
        time: "1 giờ trước",
        unread: true
      },
      {
        id: "msg-3",
        sender: "Trần Anh Tuấn",
        avatar: "TT",
        preview: "Khu đô thị mình có hỗ trợ sạc ô tô điện công cộng qua đêm không ạ?",
        time: "Hôm nay",
        unread: false
      }
    ]
  },
  website: {
    domain: "greencity.vn",
    title: "Cổng Thông tin & Dịch vụ Khu Đô Thị GreenCity",
    sslStatus: "Bảo mật SSL (Let's Encrypt Wildcard)",
    monthlyVisits: "46.800",
    uniqueVisitors: "18.200",
    uptime: "99.98%",
    seoScore: "96/100",
    banners: [
      {
        id: "bnr-1",
        title: "Không gian sống xanh - Bền vững chuẩn quốc tế",
        tag: "Banner Trang chủ",
        active: true,
        image: "https://images.unsplash.com/photo-1486406146926-c627a92ad1ab?auto=format&fit=crop&w=600&q=80"
      },
      {
        id: "bnr-2",
        title: "Ra mắt Cổng thanh toán phí dịch vụ trực tuyến không tiền mặt",
        tag: "Tiện ích số",
        active: true,
        image: "https://images.unsplash.com/photo-1556742049-0a67e5572293?auto=format&fit=crop&w=600&q=80"
      },
      {
        id: "bnr-3",
        title: "Đăng ký tham quan & Trải nghiệm tiện ích thể thao",
        tag: "Sự kiện",
        active: false,
        image: "https://images.unsplash.com/photo-1534438327276-14e5300c3a48?auto=format&fit=crop&w=600&q=80"
      }
    ],
    articles: [
      {
        id: "art-1",
        title: "Nghị quyết Hội nghị Cư dân Thường niên năm 2026 - Phân khu Grand Park",
        category: "Thông báo BQL",
        views: 3420,
        publishedDate: "05/09/2026",
        status: "Đã xuất bản"
      },
      {
        id: "art-2",
        title: "Quy chế quản lý thi công nội thất và an toàn lao động trong tòa nhà",
        category: "Quy chế & Hướng dẫn",
        views: 2150,
        publishedDate: "01/09/2026",
        status: "Đã xuất bản"
      },
      {
        id: "art-3",
        title: "Biểu phí trông giữ phương tiện giao thông áp dụng từ Q4/2026",
        category: "Tài chính & Biểu phí",
        views: 5890,
        publishedDate: "28/08/2026",
        status: "Đã xuất bản"
      }
    ],
    onlineSubmissions: [
      {
        id: "sub-1",
        formType: "Đăng ký thi công hoàn thiện căn hộ",
        resident: "Lê Văn Hùng (Căn A805)",
        date: "Hôm nay, 14:15",
        status: "Chờ duyệt hồ sơ"
      },
      {
        id: "sub-2",
        formType: "Đăng ký cấp thẻ xe ô tô cư dân",
        resident: "Ngô Thị Bích (Căn B1502)",
        date: "Hôm nay, 11:30",
        status: "Đã phê duyệt"
      }
    ]
  }
};

export const amenitiesData = {
  summary: {
    totalHospitals: 2,
    totalSchools: 3,
    totalParkingSpaces: 2180,
    availableParking: 327,
    evChargingStations: 24,
    totalStores: 42,
    activeMalls: 2,
    pendingRegistrations: 3
  },
  hospitals: [
    {
      id: "hosp-1",
      name: "Bệnh viện Đa khoa Quốc tế GreenCity",
      type: "Bệnh viện Đa khoa Quốc tế",
      badge: "Cấp cứu 24/7",
      hotline: "1900 6868 - (024) 3888 9999",
      location: "Phân khu Y tế - Đại lộ Green Boulevard",
      scale: "500 giường bệnh • 32 chuyên khoa",
      status: "Hoạt động 24/7",
      image: "https://images.unsplash.com/photo-1586773860418-d37222d8fce3?auto=format&fit=crop&w=600&q=80",
      services: ["Cấp cứu ngoại viện", "Khoa Nhi & Tiêm chủng", "Trung tâm Chẩn đoán hình ảnh MRI", "Khám sức khỏe tổng quát"]
    },
    {
      id: "hosp-2",
      name: "Phòng khám Gia đình GreenCity Family Clinic",
      type: "Phòng khám Đa khoa Gia đình",
      badge: "Khám tại nhà",
      hotline: "0982 345 678",
      location: "Tầng 1 - Tháp Grand Park A",
      scale: "Bác sĩ gia đình • Lấy mẫu xét nghiệm tại căn hộ",
      status: "07:30 - 21:00 hàng ngày",
      image: "https://images.unsplash.com/photo-1519494026892-80bbd2d6fd0d?auto=format&fit=crop&w=600&q=80",
      services: ["Khám Nội tổng quát", "Nhà thuốc GPP", "Chăm sóc sau sinh", "Bác sĩ gia đình"]
    }
  ],
  schools: [
    {
      id: "sch-1",
      name: "Trường Liên cấp Quốc tế GreenCity Academy",
      type: "Hệ thống Song ngữ & Quốc tế",
      badge: "Cambridge Partner",
      hotline: "(024) 7100 8888",
      location: "Phân khu Giáo dục - Cụm trường học A",
      levels: "Mầm non, Tiểu học, THCS & THPT",
      studentsCount: "2.450 học sinh",
      status: "Đang tuyển sinh 2026 - 2027",
      image: "https://images.unsplash.com/photo-1580582932707-520aed937b7b?auto=format&fit=crop&w=600&q=80",
      highlights: ["Chứng chỉ Cambridge Quốc tế", "Hồ bơi 4 mùa & Sân bóng đá tiêu chuẩn FIFA", "Xe Bus đưa đón tận sảnh căn hộ"]
    },
    {
      id: "sch-2",
      name: "Trường Mầm non Sinh thái GreenSprout Kindergarten",
      type: "Mầm non Tiêu chuẩn Quốc tế",
      badge: "Montessori & Reggio Emilia",
      hotline: "0915 222 333",
      location: "Khuôn viên Công viên Trung tâm",
      levels: "Nhóm trẻ 12 tháng - 5 tuổi",
      studentsCount: "380 bé",
      status: "Hoạt động",
      image: "https://images.unsplash.com/photo-1509062522246-3755977927d7?auto=format&fit=crop&w=600&q=80",
      highlights: ["Thực đơn hữu cơ 100%", "Camera trực tuyến phụ huynh", "Khu vui chơi cát và vườn rau sinh thái"]
    }
  ],
  parkingLots: [
    {
      id: "pkg-1",
      name: "Bãi xe ngầm Tháp Grand Park A",
      location: "Tầng hầm B1 & B2 - Tòa Park A",
      cars: { total: 150, occupied: 108, available: 42 },
      motorbikes: { total: 600, occupied: 420, available: 180 },
      evCharging: { total: 12, available: 6 },
      status: "Hoạt động ổn định (Cảm biến từ thông minh)",
      feeCar: "1.250.000 đ/tháng",
      feeMotor: "90.000 đ/tháng"
    },
    {
      id: "pkg-2",
      name: "Bãi xe ngầm Tháp Grand Park B",
      location: "Tầng hầm B1 & B2 - Tòa Park B",
      cars: { total: 150, occupied: 135, available: 15 },
      motorbikes: { total: 600, occupied: 510, available: 90 },
      evCharging: { total: 12, available: 4 },
      status: "Sắp đầy chỗ ô tô",
      feeCar: "1.250.000 đ/tháng",
      feeMotor: "90.000 đ/tháng"
    },
    {
      id: "pkg-3",
      name: "Bãi đỗ xe Nhanh & Xe khách Vãng lai",
      location: "Mặt đất - Cổng kiểm soát phía Tây",
      cars: { total: 80, occupied: 35, available: 45 },
      motorbikes: { total: 150, occupied: 40, available: 110 },
      evCharging: { total: 6, available: 3 },
      status: "Thu phí tự động không dừng (RFID / VietQR)",
      feeCar: "20.000 đ/lượt 2h",
      feeMotor: "5.000 đ/lượt"
    }
  ],
  shoppingCenters: [
    {
      id: "mall-1",
      name: "GreenCity Mega Mall",
      type: "Trung tâm Thương mại phức hợp 5 tầng",
      scale: "45.000 m² sàn",
      hotline: "1900 7878",
      floors: "5 tầng nổi + 1 tầng hầm",
      keyTenants: "Rạp chiếu phim CGV, Siêu thị Aeon MaxValu, Uniqlo, Manwah Hotpot",
      occupancyRate: "94%",
      openHours: "09:30 - 22:00",
      image: "https://images.unsplash.com/photo-1519567241046-7f570eee3ce6?auto=format&fit=crop&w=600&q=80"
    },
    {
      id: "mall-2",
      name: "Tuyến phố Đi bộ Thương mại Shophouse Grand Walk",
      type: "Phố Shophouse Chân đế & Thương mại dịch vụ",
      scale: "68 căn Shophouse 2 tầng",
      hotline: "024 3999 1111",
      keyTenants: "Highlands, Starbucks, Pharmacity, WinMart+, Spa & Gym",
      occupancyRate: "88%",
      openHours: "06:00 - 23:30",
      image: "https://images.unsplash.com/photo-1555396273-367ea4eb4db5?auto=format&fit=crop&w=600&q=80"
    }
  ],
  stores: [
    {
      id: "str-1",
      name: "Siêu thị WinMart+",
      category: "Bán lẻ & Tiêu dùng",
      location: "Shophouse A02 - Tòa Park A",
      phone: "024 7109 9901",
      hours: "06:00 - 22:30",
      status: "Đang mở cửa",
      revenueShare: "Thuê cố định + phí DV",
      logoText: "WM"
    },
    {
      id: "str-2",
      name: "Highlands Coffee",
      category: "F&B / Đồ uống",
      location: "Shophouse A01 - Sảnh chính Park A",
      phone: "024 7108 8802",
      hours: "06:30 - 23:00",
      status: "Đang mở cửa",
      revenueShare: "Thuê cố định",
      logoText: "HL"
    },
    {
      id: "str-3",
      name: "Nhà thuốc Tiện lợi Pharmacity",
      category: "Dược phẩm & Y tế",
      location: "Shophouse B03 - Tòa Park B",
      phone: "1800 6821",
      hours: "Mở cửa 24/7",
      status: "Đang mở cửa",
      revenueShare: "Thuê cố định",
      logoText: "PC"
    },
    {
      id: "str-4",
      name: "Cửa hàng tiện lợi GS25",
      category: "Bán lẻ & Đồ ăn nhanh",
      location: "Shophouse B01 - Phân khu Park B",
      phone: "024 7300 2525",
      hours: "Mở cửa 24/7",
      status: "Đang mở cửa",
      revenueShare: "Thuê cố định",
      logoText: "GS"
    },
    {
      id: "str-5",
      name: "Phòng tập FitZone Gym & Yoga Premium",
      category: "Thể thao & Sức khỏe",
      location: "Tầng 3 - TTTM GreenCity Mega Mall",
      phone: "0909 888 777",
      hours: "05:30 - 22:00",
      status: "Đang mở cửa",
      revenueShare: "Hợp đồng dài hạn 5 năm",
      logoText: "FZ"
    },
    {
      id: "str-6",
      name: "Tiệm giặt sấy sinh thái EcoWash",
      category: "Dịch vụ đời sống",
      location: "Shophouse A08 - Tòa Park A",
      phone: "0912 666 888",
      hours: "07:00 - 21:30",
      status: "Đang mở cửa",
      revenueShare: "Thuê cố định",
      logoText: "EW"
    }
  ],
  pendingRegistrations: [
    {
      id: "reg-101",
      brandName: "Tiệm bánh Pháp tươi Tous Les Jours",
      representative: "Đỗ Thu Trang",
      phone: "0904 123 456",
      email: "trang.do@touslesjours.vn",
      category: "F&B / Bánh tươi & Cà phê",
      desiredLocation: "Shophouse A05 - Tòa Park A (Diện tích 85 m²)",
      leaseDuration: "3 năm",
      submittedDate: "Hôm nay, 09:30",
      status: "Chờ BQL thẩm định hồ sơ",
      statusColor: "amber",
      businessLicense: "Đã nộp ĐKKD 0108928374",
      fireSafetyCommitment: true
    },
    {
      id: "reg-102",
      brandName: "Chuỗi trà Ô Long Phê La",
      representative: "Hoàng Minh Tuấn",
      phone: "0918 999 888",
      email: "tuan.hm@phela.vn",
      category: "F&B / Đồ uống",
      desiredLocation: "Kiosk K02 - Công viên Trung tâm (Diện tích 45 m²)",
      leaseDuration: "2 năm",
      submittedDate: "Hôm qua, 16:00",
      status: "Đang kiểm tra an toàn PCCC",
      statusColor: "blue",
      businessLicense: "Đã nộp ĐKKD 0109887766",
      fireSafetyCommitment: true
    },
    {
      id: "reg-103",
      brandName: "Trung tâm Anh ngữ ILA Junior",
      representative: "Lê Hải Đăng",
      phone: "0983 555 777",
      email: "dang.le@ila.edu.vn",
      category: "Giáo dục & Đào tạo",
      desiredLocation: "Tầng 2 Shophouse B10 - B12 (Diện tích 220 m²)",
      leaseDuration: "5 năm",
      submittedDate: "04/09/2026",
      status: "Đã duyệt - Chờ ký hợp đồng",
      statusColor: "emerald",
      businessLicense: "Đã nộp Giấy phép Sở GD&ĐT",
      fireSafetyCommitment: true
    }
  ]
};
