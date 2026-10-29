"""Persistent local GreenCity database. Secrets remain in the protected .local folder."""
import argparse
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
from sqlalchemy import text
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
LOCAL = ROOT / '.local'
CONFIG = LOCAL / 'database.json'
PG_BIN = Path(r'C:\Program Files\PostgreSQL\18\bin')
OPENSSL = Path(r'C:\Program Files\Git\usr\bin\openssl.exe')


def protect(path):
    if os.name == 'nt':
        owner = os.environ.get('USERDOMAIN', '') + '\\' + os.environ['USERNAME']
        subprocess.run(['icacls', str(path), '/inheritance:r', '/grant:r', owner + ':(OI)(CI)F'],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                       creationflags=subprocess.CREATE_NO_WINDOW)
    else: path.chmod(0o700)


def run(args, env=None):
    result = subprocess.run([str(a) for a in args], cwd=ROOT, env=env, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, timeout=180, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode: raise RuntimeError('Lệnh khởi tạo thất bại; xem nhật ký cục bộ, thông tin kết nối được giữ kín.')


def open_port(port):
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=.2): return True
    except OSError: return False


def pgctl(config, operation):
    data = LOCAL / 'postgres'
    if not data.is_relative_to(LOCAL.resolve()): raise RuntimeError('Invalid database path')
    command = [str(PG_BIN / 'pg_ctl.exe'), '-D', str(data), '-w', '-t', '45']
    if operation == 'start': command += ['-l', str(LOCAL / 'postgres.log')]
    command += [operation]
    process = subprocess.Popen(command, cwd=ROOT, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    try:
        until = time.monotonic() + 50
        while time.monotonic() < until:
            if open_port(config['port']) == (operation == 'start'): return
            time.sleep(.1)
        raise RuntimeError('PostgreSQL chưa đạt trạng thái yêu cầu; xem .local/postgres.log.')
    finally:
        if process.poll() is None: process.terminate()


def create():
    LOCAL.mkdir(exist_ok=True); protect(LOCAL)
    if CONFIG.is_file(): return json.loads(CONFIG.read_text(encoding='utf-8'))
    if (LOCAL / 'postgres').exists(): raise RuntimeError('Đã có thư mục dữ liệu chưa có cấu hình; giữ nguyên để kiểm tra.')
    config = {'port': 55432, 'password': secrets.token_urlsafe(32), 'secret': secrets.token_urlsafe(48)}
    if open_port(config['port']):
        with socket.socket() as s: s.bind(('127.0.0.1', 0)); config['port'] = s.getsockname()[1]
    pw = LOCAL / 'init-password.txt'; pw.write_text(config['password']+'\n', encoding='utf-8')
    try:
        run([PG_BIN / 'initdb.exe', '-D', LOCAL / 'postgres', '-U', 'greencity_owner', '--auth=scram-sha-256', '--encoding=UTF8', '--locale=C', '--pwfile', pw])
    finally: pw.unlink(missing_ok=True)
    run([OPENSSL, 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', LOCAL / 'key.pem', '-out', LOCAL / 'cert.pem', '-days', '3650', '-subj', '/CN=localhost', '-addext', 'subjectAltName=DNS:localhost,IP:127.0.0.1'])
    with (LOCAL / 'postgres' / 'postgresql.conf').open('a', encoding='utf-8') as f:
        f.write(f"\nlisten_addresses='127.0.0.1'\nport={config['port']}\nssl=on\nssl_cert_file='{(LOCAL/'cert.pem').as_posix()}'\nssl_key_file='{(LOCAL/'key.pem').as_posix()}'\nunix_socket_directories=''\n")
    CONFIG.write_text(json.dumps(config), encoding='utf-8')
    return config


def initialize(config):
    from app.core.config import Settings
    from app.core.database import Database
    url = f"postgresql://greencity_owner:{config['password']}@127.0.0.1:{config['port']}"
    cert = LOCAL / 'cert.pem'
    control = Database(Settings(database_url=url+'/postgres', database_ssl_root_cert=cert, _env_file=None))
    try:
        with control.engine.connect().execution_options(isolation_level='AUTOCOMMIT') as conn:
            if not conn.scalar(text("SELECT 1 FROM pg_database WHERE datname='greencity'")): conn.execute(text('CREATE DATABASE greencity'))
    finally: control.close()
    env = dict(os.environ, DATABASE_URL=url+'/greencity', DATABASE_SSL_ROOT_CERT=str(cert),
               SECRET_KEY=config['secret'], GREENCITY_DISABLE_DOTENV='1')
    run([sys.executable, '-m', 'scripts.migrate', 'upgrade', 'head'], env)
    database = Database(Settings(database_url=url+'/greencity', database_ssl_root_cert=cert, _env_file=None))
    try:
        if not config.get('seeded'):
            from scripts.seed import seed_database, DEMO_ACCOUNT_USERNAMES
            credentials = {u: secrets.token_urlsafe(24) for u in DEMO_ACCOUNT_USERNAMES}
            usernames = {'admin_demo': 'admin_greencity'}
            accounts = [{'username': usernames.get(u, u), 'password': p} for u,p in credentials.items()]
            (LOCAL / 'accounts.json').write_text(json.dumps(accounts, ensure_ascii=False, indent=2), encoding='utf-8')
            with database.get_session() as session:
                seed_database(session, credentials, account_usernames=usernames); session.commit()
            config['seeded'] = True; CONFIG.write_text(json.dumps(config), encoding='utf-8')
        with database.engine.connect() as conn:
            revision = conn.scalar(text('SELECT version_num FROM greencity.alembic_version'))
            count = conn.scalar(text("SELECT count(*) FROM information_schema.tables WHERE table_schema='greencity'"))
            print(f'GreenCity database: ready; revision={revision}; tables={count}; port={config["port"]}')
    finally: database.close()
    # Last: ordinary application startup picks up the new database after successful setup.
    application = LOCAL / 'application.env'
    managed = {'DATABASE_URL','DATABASE_SSL_ROOT_CERT','SECRET_KEY','APP_ENV','PRIVATE_STORAGE_PATH'}
    other = [line for line in application.read_text(encoding='utf-8').splitlines() if line.split('=',1)[0].strip() not in managed] if application.exists() else []
    application.write_text(f'DATABASE_URL={url}/greencity\nDATABASE_SSL_ROOT_CERT="{cert.as_posix()}"\nSECRET_KEY={config["secret"]}\nAPP_ENV=development\nPRIVATE_STORAGE_PATH="{(LOCAL/"documents").as_posix()}"\n' + '\n'.join(other) + '\n', encoding='utf-8')


def backup(config):
    """Reuse the existing dump/evidence/checksum backup implementation."""
    import runpy
    worker = runpy.run_path(str(ROOT.parent / 'deploy' / 'backup_loop.py'))
    url = f"postgresql://greencity_owner:{config['password']}@127.0.0.1:{config['port']}/greencity?sslmode=verify-full&sslrootcert={quote((LOCAL/'cert.pem').as_posix(),safe='')}"
    previous_path = os.environ.get('PATH','')
    try:
        os.environ['PATH'] = str(PG_BIN) + os.pathsep + previous_path
        result = worker['create_backup'](url, LOCAL / 'backups', LOCAL / 'documents')
        print(json.dumps(result,ensure_ascii=False))
    finally: os.environ['PATH'] = previous_path


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('operation', choices=['init', 'start', 'stop', 'status', 'backup'], nargs='?', default='init'); args = parser.parse_args()
    if args.operation == 'init':
        config = create()
        if not open_port(config['port']): pgctl(config, 'start')
        initialize(config)
    else:
        if not CONFIG.is_file(): raise RuntimeError('Chưa khởi tạo database; chạy init trước.')
        config = json.loads(CONFIG.read_text(encoding='utf-8'))
        if args.operation == 'status': print('PostgreSQL: ' + ('running' if open_port(config['port']) else 'stopped'))
        elif args.operation == 'backup':
            if not open_port(config['port']): raise RuntimeError('Database cần chạy trước khi sao lưu.')
            backup(config)
        elif args.operation == 'start':
            if not open_port(config['port']): pgctl(config, 'start')
            initialize(config)
        elif open_port(config['port']): pgctl(config, 'stop')


if __name__ == '__main__':
    try: main()
    except Exception:
        print('Khởi tạo chưa thành công; thông tin kết nối và mật khẩu không được ghi ra màn hình.', file=sys.stderr)
        sys.exit(1)
