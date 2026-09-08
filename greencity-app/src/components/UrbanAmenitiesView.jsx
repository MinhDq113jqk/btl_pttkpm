import React, { useState } from 'react';
import { 
  Building2, 
  Store, 
  GraduationCap,
  Sparkles,
  HeartPulse, 
  Car, 
  ShoppingBag, 
  Plus, 
  Phone, 
  MapPin, 
  CheckCircle2, 
  Clock, 
  Zap, 
  AlertCircle, 
  FileText, 
  UploadCloud, 
  Send, 
  ArrowRight,
  ShieldCheck,
  Check,
  Search,
  Filter,
  Eye,
  Calendar
} from 'lucide-react';
import { amenitiesData } from '../data/mockData';
import { Dialog } from './Dialog';
import { PreviewImage } from './PreviewImage';

export const UrbanAmenitiesView = ({ onToast }) => {
  const [activeTab, setActiveTab] = useState('overview'); // 'overview' | 'parking' | 'merchants' | 'registration' | 'hospital_school'
  const [merchantCategory, setMerchantCategory] = useState('all');

  // Vendor Registration Form State
  const [vendorForm, setVendorForm] = useState({
    brandName: '',
    representative: '',
    phone: '',
    email: '',
    category: 'F&B / Đồ uống & Nhà hàng',
    desiredLocation: 'Shophouse Chân đế - Tòa Grand Park A',
    areaRequested: '75',
    leaseDuration: '3 năm',
    businessLicenseNumber: '',
    pcccCommitment: true,
    foodSafetyCommitment: true,
    remarks: ''
  });

  const [registrationsList, setRegistrationsList] = useState(amenitiesData.pendingRegistrations);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [selectedRegistration, setSelectedRegistration] = useState(null);
  const [savedVendor, setSavedVendor] = useState(null);
  const summary = {
    ...amenitiesData.summary,
    totalHospitals: amenitiesData.hospitals.length,
    totalSchools: amenitiesData.schools.length,
    totalStores: amenitiesData.stores.length,
    availableParking: amenitiesData.parkingLots.reduce((count, lot) => count + lot.cars.available + lot.motorbikes.available, 0),
    totalParkingSpaces: amenitiesData.parkingLots.reduce((count, lot) => count + lot.cars.total + lot.motorbikes.total, 0),
    evChargingStations: amenitiesData.parkingLots.reduce((count, lot) => count + lot.evCharging.total, 0),
    availableCharging: amenitiesData.parkingLots.reduce((count, lot) => count + lot.evCharging.available, 0),
  };

  const handleVendorSubmit = (e) => {
    e.preventDefault();
    if (isSubmitting) return;
    if (!vendorForm.brandName || !vendorForm.representative || !vendorForm.phone) {
      onToast?.('Vui lòng điền đầy đủ các trường bắt buộc (*)', 'warning');
      return;
    }

    setIsSubmitting(true);
    setTimeout(() => {
      const newReg = {
        id: `reg-${Date.now()}`,
        brandName: vendorForm.brandName,
        representative: vendorForm.representative,
        phone: vendorForm.phone,
        email: vendorForm.email,
        category: vendorForm.category,
        desiredLocation: `${vendorForm.desiredLocation} (${vendorForm.areaRequested} m²)`,
        leaseDuration: vendorForm.leaseDuration,
        submittedDate: 'Vừa xong',
        status: 'Chờ BQL thẩm định hồ sơ',
        statusColor: 'amber',
        businessLicense: `ĐKKD: ${vendorForm.businessLicenseNumber || 'Đang bổ sung'}`,
        fireSafetyCommitment: vendorForm.pcccCommitment
      };

      setRegistrationsList([newReg, ...registrationsList]);
      setIsSubmitting(false);
      onToast?.('Đã thêm hồ sơ vào danh sách mẫu trong phiên này. Chưa gửi đến Ban quản lý.', 'info');
      setSavedVendor(null);

      // Reset form & view list
      setVendorForm({
        brandName: '',
        representative: '',
        phone: '',
        email: '',
        category: 'F&B / Đồ uống & Nhà hàng',
        desiredLocation: 'Shophouse Chân đế - Tòa Grand Park A',
        areaRequested: '75',
        leaseDuration: '3 năm',
        businessLicenseNumber: '',
        pcccCommitment: true,
        foodSafetyCommitment: true,
        remarks: ''
      });
      setActiveTab('registration');
      setSelectedRegistration(newReg);
    }, 1000);
  };

  const filteredStores = amenitiesData.stores.filter(s => {
    if (merchantCategory === 'all') return true;
    if (merchantCategory === 'fnb') return s.category.includes('F&B');
    if (merchantCategory === 'retail') return s.category.includes('Bán lẻ');
    if (merchantCategory === 'health') return s.category.includes('Y tế') || s.category.includes('Sức khỏe');
    return true;
  });

  return (
    <div className="p-4 sm:p-8 max-w-7xl mx-auto space-y-6 pb-24">
      {/* Page Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-emerald-700">
            <span>GREENCITY</span>
            <span>/</span>
            <span className="text-slate-400">HỆ SINH THÁI TIỆN ÍCH</span>
          </div>
          <h1 className="text-2xl font-bold text-slate-900 mt-1">
            Tiện ích Đô thị & Gian hàng Thương mại
          </h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Bệnh viện, Trường học, Bãi đỗ xe thông minh, Trung tâm thương mại và Cổng đăng ký kinh doanh Shophouse.
          </p>
        </div>

        {/* Action Button: Đăng ký kinh doanh */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => setActiveTab('registration')}
            className="flex items-center gap-2 px-4 py-2.5 bg-emerald-700 hover:bg-emerald-800 active:bg-emerald-800 text-white rounded-xl text-xs font-bold shadow-sm shadow-emerald-600/20 transition-all cursor-pointer"
          >
            <Plus size={16} />
            <span>Đăng ký mở gian hàng mới</span>
          </button>
        </div>
      </div>

      {/* 4 Amenity KPI Cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <button type="button"
          onClick={() => setActiveTab('hospital_school')}
          className="bg-white rounded-2xl p-4 border border-slate-200/90 shadow-2xs hover:border-emerald-300 hover:shadow-sm transition-all cursor-pointer group"
        >
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold text-slate-500">Y tế & Sức khỏe</span>
            <div className="w-8 h-8 rounded-xl bg-rose-50 text-rose-600 flex items-center justify-center group-hover:scale-105 transition-transform">
              <HeartPulse size={17} />
            </div>
          </div>
          <p className="text-2xl font-bold text-slate-900">{summary.totalHospitals} Cơ sở</p>
          <p className="text-xs text-emerald-700 font-medium mt-0.5">● Bệnh viện Quốc tế 24/7</p>
        </button>

        <button type="button"
          onClick={() => setActiveTab('hospital_school')}
          className="bg-white rounded-2xl p-4 border border-slate-200/90 shadow-2xs hover:border-emerald-300 hover:shadow-sm transition-all cursor-pointer group"
        >
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold text-slate-500">Trường học & Giáo dục</span>
            <div className="w-8 h-8 rounded-xl bg-indigo-50 text-indigo-600 flex items-center justify-center group-hover:scale-105 transition-transform">
              <GraduationCap size={17} />
            </div>
          </div>
          <p className="text-2xl font-bold text-slate-900">{summary.totalSchools} Hệ thống</p>
          <p className="text-xs text-indigo-700 font-medium mt-0.5">Liên cấp & Mầm non sinh thái</p>
        </button>

        <button type="button"
          onClick={() => setActiveTab('parking')}
          className="bg-white rounded-2xl p-4 border border-slate-200/90 shadow-2xs hover:border-emerald-300 hover:shadow-sm transition-all cursor-pointer group"
        >
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold text-slate-500">Bãi đỗ xe thông minh</span>
            <div className="w-8 h-8 rounded-xl bg-blue-50 text-blue-600 flex items-center justify-center group-hover:scale-105 transition-transform">
              <Car size={17} />
            </div>
          </div>
          <p className="text-2xl font-bold text-slate-900">{summary.availableParking} Chỗ trống</p>
          <p className="text-xs text-emerald-700 font-medium mt-0.5">{summary.evChargingStations} Cổng sạc ô tô điện EV</p>
        </button>

        <button type="button"
          onClick={() => setActiveTab('merchants')}
          className="bg-white rounded-2xl p-4 border border-slate-200/90 shadow-2xs hover:border-emerald-300 hover:shadow-sm transition-all cursor-pointer group"
        >
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold text-slate-500">Thương mại & Gian hàng</span>
            <div className="w-8 h-8 rounded-xl bg-amber-50 text-amber-600 flex items-center justify-center group-hover:scale-105 transition-transform">
              <Store size={17} />
            </div>
          </div>
          <p className="text-2xl font-bold text-slate-900">{summary.totalStores} Cửa hàng</p>
          <p className="text-xs text-amber-700 font-medium mt-0.5">{registrationsList.length} Hồ sơ đăng ký</p>
        </button>
      </div>

      {/* Navigation Sub-Tabs */}
      <div className="flex items-center gap-2 border-b border-slate-200 overflow-x-auto pb-1 text-xs">
        <button
          onClick={() => setActiveTab('overview')}
          className={`px-4 py-2.5 rounded-xl font-bold transition-all flex items-center gap-2 ${
            activeTab === 'overview'
              ? 'bg-emerald-50 text-emerald-700 border border-emerald-200 shadow-2xs'
              : 'text-slate-600 hover:bg-slate-50'
          }`}
        >
          <Building2 size={15} />
          <span>Tổng quan Hệ sinh thái</span>
        </button>

        <button
          onClick={() => setActiveTab('parking')}
          className={`px-4 py-2.5 rounded-xl font-bold transition-all flex items-center gap-2 ${
            activeTab === 'parking'
              ? 'bg-blue-50 text-blue-700 border border-blue-200 shadow-2xs'
              : 'text-slate-600 hover:bg-slate-50'
          }`}
        >
          <Car size={15} />
          <span>Bãi đỗ xe thông minh ({summary.availableParking} trống)</span>
        </button>

        <button
          onClick={() => setActiveTab('merchants')}
          className={`px-4 py-2.5 rounded-xl font-bold transition-all flex items-center gap-2 ${
            activeTab === 'merchants'
              ? 'bg-amber-50 text-amber-700 border border-amber-200 shadow-2xs'
              : 'text-slate-600 hover:bg-slate-50'
          }`}
        >
          <Store size={15} />
          <span>Cửa hàng & TTTM ({summary.totalStores})</span>
        </button>

        <button
          onClick={() => setActiveTab('registration')}
          className={`px-4 py-2.5 rounded-xl font-bold transition-all flex items-center gap-2 ${
            activeTab === 'registration'
              ? 'bg-slate-900 text-white shadow-2xs'
              : 'text-slate-600 hover:bg-slate-50'
          }`}
        >
          <Plus size={15} />
          <span>Đăng ký mở gian hàng ({registrationsList.length})</span>
        </button>

        <button
          onClick={() => setActiveTab('hospital_school')}
          className={`px-4 py-2.5 rounded-xl font-bold transition-all flex items-center gap-2 ${
            activeTab === 'hospital_school'
              ? 'bg-rose-50 text-rose-700 border border-rose-200 shadow-2xs'
              : 'text-slate-600 hover:bg-slate-50'
          }`}
        >
          <HeartPulse size={15} />
          <span>Bệnh viện & Trường học</span>
        </button>
      </div>

      {/* TAB 1: TỔNG QUAN HỆ SINH THÁI */}
      {activeTab === 'overview' && (
        <div className="space-y-6">
          {/* Mega Mall & Shophouse Feature Banner */}
          <div className="rounded-3xl bg-gradient-to-r from-slate-900 via-emerald-950 to-slate-900 p-6 sm:p-8 text-white shadow-xl relative overflow-hidden">
            <div className="relative z-10 max-w-2xl space-y-3">
              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-500/20 text-emerald-300 text-xs font-semibold border border-emerald-400/30">
                <Sparkles size={13} />
                <span>Tiện ích All-In-One Đạt Chuẩn 5 Sao</span>
              </span>
              <h2 className="text-2xl sm:text-3xl font-bold tracking-tight">
                Không gian sống trọn vẹn tại GreenCity
              </h2>
              <p className="text-slate-300 text-xs sm:text-sm leading-relaxed">
                Hệ sinh thái tiện ích tích hợp đồng bộ: Bệnh viện Quốc tế, Trường học liên cấp Cambridge, Đại siêu thị & TTTM Mega Mall, Hệ thống bãi xe thông minh kết hợp trạm sạc điện xanh.
              </p>
            </div>
          </div>

          {/* 3 Columns: Quick Previews */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Column 1: Y tế & Giáo dục */}
            <div className="bg-white rounded-2xl border border-slate-200/90 shadow-xs p-5 space-y-4">
              <div className="flex items-center justify-between pb-3 border-b border-slate-100">
                <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                  <HeartPulse size={16} className="text-rose-600" />
                  <span>Y tế & Trường học</span>
                </h3>
                <button onClick={() => setActiveTab('hospital_school')} className="text-xs font-bold text-emerald-700 hover:underline">
                  Xem chi tiết →
                </button>
              </div>

              <div className="space-y-3 text-xs">
                <div className="p-3 rounded-xl bg-slate-50 border border-slate-200/60 space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-slate-800">BVĐK Quốc tế GreenCity</span>
                    <span className="text-xs bg-rose-100 text-rose-800 font-bold px-1.5 py-0.5 rounded">24/7</span>
                  </div>
                  <p className="text-xs text-slate-500">Hotline cấp cứu: 1900 6868</p>
                </div>

                <div className="p-3 rounded-xl bg-slate-50 border border-slate-200/60 space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-slate-800">Trường Quốc tế GreenCity</span>
                    <span className="text-xs bg-indigo-100 text-indigo-800 font-bold px-1.5 py-0.5 rounded">K-12</span>
                  </div>
                  <p className="text-xs text-slate-500">Tuyển sinh: 2026 - 2027</p>
                </div>
              </div>
            </div>

            {/* Column 2: Bãi xe thông minh */}
            <div className="bg-white rounded-2xl border border-slate-200/90 shadow-xs p-5 space-y-4">
              <div className="flex items-center justify-between pb-3 border-b border-slate-100">
                <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                  <Car size={16} className="text-blue-600" />
                  <span>Chỗ đỗ xe khả dụng</span>
                </h3>
                <button onClick={() => setActiveTab('parking')} className="text-xs font-bold text-emerald-700 hover:underline">
                  Quản lý bãi xe →
                </button>
              </div>

              <div className="space-y-2.5 text-xs">
                <div className="flex justify-between items-center p-2.5 rounded-xl bg-slate-50">
                  <span className="text-slate-600">Hầm B1-B2 Tháp Park A</span>
                  <span className="font-bold text-emerald-700">42 ô tô • 180 xe máy</span>
                </div>
                <div className="flex justify-between items-center p-2.5 rounded-xl bg-slate-50">
                  <span className="text-slate-600">Hầm B1-B2 Tháp Park B</span>
                  <span className="font-bold text-amber-700">15 ô tô • 90 xe máy</span>
                </div>
                <div className="flex justify-between items-center p-2.5 rounded-xl bg-emerald-50 text-emerald-900 font-medium">
                  <span className="flex items-center gap-1.5">
                    <Zap size={13} className="text-emerald-700" />
                    <span>Trạm sạc xe điện EV</span>
                  </span>
                  <span className="font-bold">{summary.availableCharging}/{summary.evChargingStations} cổng trống</span>
                </div>
              </div>
            </div>

            {/* Column 3: Gian hàng & Cửa hàng */}
            <div className="bg-white rounded-2xl border border-slate-200/90 shadow-xs p-5 space-y-4">
              <div className="flex items-center justify-between pb-3 border-b border-slate-100">
                <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2">
                  <Store size={16} className="text-amber-600" />
                  <span>Gian hàng nổi bật</span>
                </h3>
                <button onClick={() => setActiveTab('merchants')} className="text-xs font-bold text-emerald-700 hover:underline">
                  Xem tất cả →
                </button>
              </div>

              <div className="space-y-2 text-xs">
                {amenitiesData.stores.slice(0, 3).map((s) => (
                  <div key={s.id} className="p-2.5 rounded-xl bg-slate-50 flex items-center justify-between">
                    <div>
                      <p className="font-bold text-slate-800">{s.name}</p>
                      <p className="text-xs text-slate-400">{s.location}</p>
                    </div>
                    <span className="text-xs bg-emerald-100 text-emerald-800 font-bold px-2 py-0.5 rounded-full">
                      {s.status}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: BÃI ĐỖ XE THÔNG MINH */}
      {activeTab === 'parking' && (
        <div className="space-y-6">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
            {amenitiesData.parkingLots.map((lot) => {
              const carPercent = Math.round((lot.cars.occupied / lot.cars.total) * 100);
              const motorPercent = Math.round((lot.motorbikes.occupied / lot.motorbikes.total) * 100);

              return (
                <div key={lot.id} className="bg-white rounded-2xl border border-slate-200/90 shadow-xs p-6 space-y-4">
                  <div className="flex items-start justify-between">
                    <div>
                      <h3 className="text-sm font-bold text-slate-900">{lot.name}</h3>
                      <p className="text-xs text-slate-400 flex items-center gap-1 mt-0.5">
                        <MapPin size={12} />
                        <span>{lot.location}</span>
                      </p>
                    </div>
                    <span className="text-xs px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 font-bold border border-blue-200">
                      Cảm biến RFID
                    </span>
                  </div>

                  {/* Car Occupancy */}
                  <div className="space-y-1.5 text-xs">
                    <div className="flex justify-between font-medium">
                      <span className="text-slate-600 flex items-center gap-1">
                        <Car size={14} className="text-slate-500" />
                        <span>Chỗ đỗ Ô tô:</span>
                      </span>
                      <span className="font-bold text-slate-800">
                        Còn {lot.cars.available} / {lot.cars.total} chỗ
                      </span>
                    </div>
                    <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                      <div 
                        className={`h-full rounded-full ${carPercent > 85 ? 'bg-rose-500' : 'bg-emerald-500'}`}
                        style={{ width: `${carPercent}%` }}
                      />
                    </div>
                  </div>

                  {/* Motorbike Occupancy */}
                  <div className="space-y-1.5 text-xs">
                    <div className="flex justify-between font-medium">
                      <span className="text-slate-600">Chỗ đỗ Xe máy:</span>
                      <span className="font-bold text-slate-800">
                        Còn {lot.motorbikes.available} / {lot.motorbikes.total} chỗ
                      </span>
                    </div>
                    <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                      <div 
                        className="h-full rounded-full bg-blue-500"
                        style={{ width: `${motorPercent}%` }}
                      />
                    </div>
                  </div>

                  {/* EV Charging Station */}
                  <div className="p-3 rounded-xl bg-emerald-50/70 border border-emerald-200/80 flex items-center justify-between text-xs text-emerald-900">
                    <div className="flex items-center gap-2">
                      <Zap size={16} className="text-emerald-700" />
                      <span className="font-bold">Trạm sạc xe điện EV</span>
                    </div>
                    <span className="font-bold text-emerald-800">{lot.evCharging.available}/{lot.evCharging.total} cổng trống</span>
                  </div>

                  {/* Fees & Status */}
                  <div className="pt-2 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
                    <span>Phí ô tô: <strong className="text-slate-700">{lot.feeCar}</strong></span>
                    <span className="text-emerald-700 font-semibold">{lot.status}</span>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* TAB 3: GIAN HÀNG & CỬA HÀNG THƯƠNG MẠI */}
      {activeTab === 'merchants' && (
        <div className="space-y-6">
          {/* Shopping Malls Highlight */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {amenitiesData.shoppingCenters.map((mall) => (
              <div key={mall.id} className="bg-white rounded-2xl border border-slate-200/90 shadow-xs overflow-hidden flex flex-col justify-between">
                <div className="relative h-44">
                  <PreviewImage src={mall.image} alt={mall.name} className="w-full h-full object-cover" />
                  <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/20 to-transparent" />
                  <div className="absolute bottom-3 left-4 right-4 text-white">
                    <span className="text-xs bg-emerald-500 text-white font-bold px-2 py-0.5 rounded">
                      {mall.type}
                    </span>
                    <h3 className="text-base font-bold mt-1">{mall.name}</h3>
                    <p className="text-xs text-slate-200 mt-0.5">Quy mô: {mall.scale} • Tỷ lệ lấp đầy: {mall.occupancyRate}</p>
                  </div>
                </div>

                <div className="p-4 space-y-2 text-xs">
                  <p className="text-slate-600">
                    <strong>Thương hiệu chính:</strong> {mall.keyTenants}
                  </p>
                  <div className="pt-2 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
                    <span>Giờ mở cửa: {mall.openHours}</span>
                    <span className="font-bold text-emerald-700">Hotline: {mall.hotline}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* Stores Directory with Category Filter */}
          <div className="bg-white rounded-2xl border border-slate-200/90 shadow-xs p-6 space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-100">
              <div>
                <h3 className="text-sm font-bold text-slate-900">Danh mục Cửa hàng đang hoạt động ({filteredStores.length})</h3>
                <p className="text-xs text-slate-400 mt-0.5">Các gian hàng Shophouse và TTTM phục vụ cư dân</p>
              </div>

              {/* Category Filter */}
              <div className="flex items-center gap-1.5 text-xs overflow-x-auto">
                <button
                  onClick={() => setMerchantCategory('all')}
                  className={`px-3 py-1.5 rounded-xl font-bold transition-all ${
                    merchantCategory === 'all' ? 'bg-slate-900 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                  }`}
                >
                  Tất cả
                </button>
                <button
                  onClick={() => setMerchantCategory('fnb')}
                  className={`px-3 py-1.5 rounded-xl font-bold transition-all ${
                    merchantCategory === 'fnb' ? 'bg-amber-600 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                  }`}
                >
                  F&B / Ẩm thực
                </button>
                <button
                  onClick={() => setMerchantCategory('retail')}
                  className={`px-3 py-1.5 rounded-xl font-bold transition-all ${
                    merchantCategory === 'retail' ? 'bg-blue-600 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                  }`}
                >
                  Siêu thị & Bán lẻ
                </button>
                <button
                  onClick={() => setMerchantCategory('health')}
                  className={`px-3 py-1.5 rounded-xl font-bold transition-all ${
                    merchantCategory === 'health' ? 'bg-rose-600 text-white' : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                  }`}
                >
                  Sức khỏe & Gym
                </button>
              </div>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {filteredStores.map((store) => (
                <div key={store.id} className="p-4 rounded-xl border border-slate-200 bg-slate-50/60 hover:bg-white hover:border-slate-300 transition-all space-y-2.5">
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2.5">
                      <div className="w-9 h-9 rounded-xl bg-slate-900 text-white font-bold text-xs flex items-center justify-center shadow-2xs">
                        {store.logoText}
                      </div>
                      <div>
                        <h4 className="text-xs font-bold text-slate-900">{store.name}</h4>
                        <span className="text-xs text-slate-400">{store.category}</span>
                      </div>
                    </div>
                    <span className="text-xs bg-emerald-100 text-emerald-800 font-bold px-2 py-0.5 rounded-full">
                      {store.status}
                    </span>
                  </div>

                  <div className="space-y-1 text-xs text-slate-600 pt-1">
                    <p className="flex items-center gap-1 text-xs">
                      <MapPin size={12} className="text-slate-400" />
                      <span>{store.location}</span>
                    </p>
                    <p className="flex items-center gap-1 text-xs">
                      <Phone size={12} className="text-slate-400" />
                      <span>{store.phone}</span>
                    </p>
                    <p className="flex items-center gap-1 text-xs">
                      <Clock size={12} className="text-slate-400" />
                      <span>{store.hours}</span>
                    </p>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* TAB 4: ĐĂNG KÝ MỞ GIAN HÀNG / THUÊ MẶT BẰNG */}
      {activeTab === 'registration' && (
        <div className="space-y-6">
          {/* Pending Applications List */}
          <div className="bg-white rounded-2xl border border-slate-200/90 shadow-xs p-6 space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div>
                <h3 className="text-sm font-bold text-slate-900">Hồ sơ Đăng ký Mở Gian hàng Đang Chờ Duyệt</h3>
                <p className="text-xs text-slate-400 mt-0.5">Danh sách các thương hiệu nộp đơn đăng ký bán hàng & thuê mặt bằng</p>
              </div>
              <span className="text-xs bg-amber-100 text-amber-800 font-bold px-2.5 py-1 rounded-full">
                {registrationsList.length} Hồ sơ
              </span>
            </div>

            <div className="space-y-3">
              {registrationsList.map((reg) => {
                const colorPill = {
                  amber: 'bg-amber-50 text-amber-800 border-amber-300',
                  blue: 'bg-blue-50 text-blue-800 border-blue-300',
                  emerald: 'bg-emerald-50 text-emerald-800 border-emerald-300'
                }[reg.statusColor] || 'bg-slate-100 text-slate-700';

                return (
                  <div key={reg.id} className="p-4 rounded-xl border border-slate-200 bg-slate-50/50 hover:bg-white transition-all space-y-2.5">
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                      <div>
                        <div className="flex items-center gap-2">
                          <h4 className="text-xs font-bold text-slate-900">{reg.brandName}</h4>
                          <span className="text-xs bg-slate-200 text-slate-700 px-1.5 py-0.2 rounded font-semibold">
                            {reg.category}
                          </span>
                        </div>
                        <p className="text-xs text-slate-500 mt-0.5">
                          Đại diện: <strong>{reg.representative}</strong> • ĐT: {reg.phone} • Ngày nộp: {reg.submittedDate}
                        </p>
                      </div>

                      <span className={`text-xs px-2.5 py-1 rounded-full font-bold border ${colorPill} self-start sm:self-auto`}>
                        {reg.status}
                      </span>
                    </div>

                    <div className="pt-2 border-t border-slate-200/60 flex flex-col sm:flex-row sm:items-center justify-between gap-2 text-xs text-slate-600">
                      <span>Vị trí đề xuất: <strong className="text-slate-800">{reg.desiredLocation}</strong> (Thời hạn: {reg.leaseDuration})</span>
                      <div className="flex items-center gap-2">
                        <span className="text-xs text-emerald-700 font-semibold flex items-center gap-1">
                          <CheckCircle2 size={13} />
                          <span>{reg.businessLicense}</span>
                        </span>
                        <button 
                          onClick={() => setSelectedRegistration(reg)}
                          className="text-xs font-bold text-blue-600 hover:underline"
                        >
                          Xem hồ sơ →
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>

          {/* Form: Đăng ký mở gian hàng mới */}
          <div className="bg-white rounded-2xl border border-slate-200/90 shadow-xs p-6 space-y-6">
            <div className="pb-4 border-b border-slate-100">
              <div className="flex items-center gap-2 text-xs font-bold text-emerald-700 uppercase">
                <Store size={15} />
                <span>Biểu mẫu Tiếp nhận & Đăng ký Thuê Mặt Bằng</span>
              </div>
              <h2 className="text-lg font-bold text-slate-900 mt-1">Đăng ký Mở Gian Hàng / Cửa Hàng Mới</h2>
              <p className="text-xs text-slate-500 mt-0.5">
                Dành cho các đơn vị kinh doanh, chuỗi bán lẻ, F&B muốn mở điểm bán hàng tại khu đô thị GreenCity.
              </p>
            </div>

            <form onSubmit={handleVendorSubmit} className="space-y-6">
              <p className="context-note">Biểu mẫu minh họa. Nội dung được giữ khi chuyển phân hệ; tải lại ứng dụng sẽ xóa dữ liệu chưa có máy chủ lưu trữ.</p>
              {savedVendor && <button type="button" className="button-secondary" onClick={() => setVendorForm({ ...savedVendor })}>Khôi phục nháp gian hàng trong phiên</button>}
              {/* SECTION 1: THÔNG TIN THƯƠNG HIỆU */}
              <div className="space-y-3">
                <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wide">1. Thông tin Thương hiệu & Đại diện</h3>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 text-xs">
                  <div className="space-y-1 sm:col-span-2">
                    <label htmlFor="vendor-brandName" className="font-bold text-slate-700">Tên thương hiệu / Cửa hàng *</label>
                    <input
                      type="text"
                      required
                      id="vendor-brandName"
                    value={vendorForm.brandName}
                      onChange={(e) => setVendorForm({ ...vendorForm, brandName: e.target.value })}
                      placeholder="Ví dụ: K Coffee & Bakery, Tiệm hoa tươi L'Amour..."
                      className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500/20 outline-none font-medium text-slate-800"
                    />
                  </div>

                  <div className="space-y-1">
                    <label htmlFor="vendor-representative" className="font-bold text-slate-700">Người đại diện pháp luật *</label>
                    <input
                      type="text"
                      required
                      id="vendor-representative"
                    value={vendorForm.representative}
                      onChange={(e) => setVendorForm({ ...vendorForm, representative: e.target.value })}
                      placeholder="Họ và tên"
                      className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500/20 outline-none font-medium text-slate-800"
                    />
                  </div>

                  <div className="space-y-1">
                    <label htmlFor="vendor-phone" className="font-bold text-slate-700">Số điện thoại liên hệ *</label>
                    <input
                      type="text"
                      required
                      id="vendor-phone"
                    value={vendorForm.phone}
                      onChange={(e) => setVendorForm({ ...vendorForm, phone: e.target.value })}
                      placeholder="09xx xxx xxx"
                      className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500/20 outline-none font-medium text-slate-800"
                    />
                  </div>
                </div>
              </div>

              {/* SECTION 2: NGÀNH HÀNG & MẶT BẰNG */}
              <div className="space-y-3 pt-2 border-t border-slate-100">
                <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wide">2. Ngành hàng & Nhu cầu Mặt bằng</h3>
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 text-xs">
                  <div className="space-y-1">
                    <label htmlFor="vendor-category" className="font-bold text-slate-700">Ngành hàng kinh doanh</label>
                    <select
                      id="vendor-category"
                    value={vendorForm.category}
                      onChange={(e) => setVendorForm({ ...vendorForm, category: e.target.value })}
                      className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500/20 outline-none font-medium text-slate-800 bg-white"
                    >
                      <option>F&B / Đồ uống & Nhà hàng</option>
                      <option>Siêu thị & Bán lẻ tiện lợi</option>
                      <option>Dược phẩm & Y tế</option>
                      <option>Thời trang & Phụ kiện</option>
                      <option>Dịch vụ đời sống (Giặt là, Spa, Salon)</option>
                      <option>Giáo dục & Đào tạo</option>
                    </select>
                  </div>

                  <div className="space-y-1 sm:col-span-2">
                    <label htmlFor="vendor-desiredLocation" className="font-bold text-slate-700">Vị trí mong muốn thuê</label>
                    <select
                      id="vendor-desiredLocation"
                    value={vendorForm.desiredLocation}
                      onChange={(e) => setVendorForm({ ...vendorForm, desiredLocation: e.target.value })}
                      className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500/20 outline-none font-medium text-slate-800 bg-white"
                    >
                      <option>Shophouse Chân đế - Tòa Grand Park A</option>
                      <option>Shophouse Chân đế - Tòa Grand Park B</option>
                      <option>Trung tâm thương mại GreenCity Mega Mall - Tầng 1</option>
                      <option>Khu ẩm thực Food Court Mega Mall - Tầng 4</option>
                      <option>Kiosk kinh doanh ngoài trời - Công viên Trung tâm</option>
                    </select>
                  </div>

                  <div className="space-y-1">
                    <label htmlFor="vendor-areaRequested" className="font-bold text-slate-700">Diện tích dự kiến (m²)</label>
                    <input
                      type="number"
                      min="1"
                      step="1"
                      required
                      id="vendor-areaRequested"
                    value={vendorForm.areaRequested}
                      onChange={(e) => setVendorForm({ ...vendorForm, areaRequested: e.target.value })}
                      className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500/20 outline-none font-bold text-slate-800"
                    />
                  </div>
                </div>
              </div>

              {/* SECTION 3: PHÁP LÝ & CAM KẾT */}
              <div className="space-y-3 pt-2 border-t border-slate-100">
                <h3 className="text-xs font-bold text-slate-800 uppercase tracking-wide">3. Hồ sơ Pháp lý & An toàn</h3>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
                  <div className="space-y-1">
                    <label htmlFor="vendor-businessLicenseNumber" className="font-bold text-slate-700">Mã số ĐKKD / Giấy phép thành lập</label>
                    <input
                      type="text"
                      id="vendor-businessLicenseNumber"
                    value={vendorForm.businessLicenseNumber}
                      onChange={(e) => setVendorForm({ ...vendorForm, businessLicenseNumber: e.target.value })}
                      placeholder="Nhập mã số thuế / ĐKKD doanh nghiệp"
                      className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500/20 outline-none font-medium text-slate-800"
                    />
                  </div>

                  <div className="space-y-2 pt-2">
                    <label className="flex items-center gap-2 cursor-pointer font-medium text-slate-700">
                      <input
                        type="checkbox"
                        checked={vendorForm.pcccCommitment}
                        onChange={(e) => setVendorForm({ ...vendorForm, pcccCommitment: e.target.checked })}
                        className="rounded text-emerald-700 focus:ring-emerald-500"
                      />
                      <span>Cam kết tuân thủ tiêu chuẩn Phòng cháy Chữa cháy (PCCC) BQL</span>
                    </label>

                    <label className="flex items-center gap-2 cursor-pointer font-medium text-slate-700">
                      <input
                        type="checkbox"
                        checked={vendorForm.foodSafetyCommitment}
                        onChange={(e) => setVendorForm({ ...vendorForm, foodSafetyCommitment: e.target.checked })}
                        className="rounded text-emerald-700 focus:ring-emerald-500"
                      />
                      <span>Cam kết tiêu chuẩn Vệ sinh An toàn Thực phẩm & Môi trường xanh</span>
                    </label>
                  </div>
                </div>
              </div>

              {/* ACTION BUTTONS */}
              <div className="flex items-center justify-between pt-4 border-t border-slate-100">
                <button
                  type="button"
                  onClick={() => setActiveTab('merchants')}
                  className="px-4 py-2.5 text-xs font-semibold text-slate-600 hover:text-slate-900 rounded-xl border border-slate-200 hover:bg-slate-100 transition-colors"
                >
                  Quay lại danh sách
                </button>

                <div className="flex items-center gap-3">
                  <button
                    type="button"
                    onClick={() => { setSavedVendor({ ...vendorForm }); onToast?.('Đã lưu nháp gian hàng trong phiên này. Tải lại ứng dụng sẽ xóa bản nháp.', 'info'); }}
                    className="px-4 py-2.5 text-xs font-semibold text-slate-700 bg-slate-50 border border-slate-300 rounded-xl hover:bg-slate-100 transition-colors"
                  >
                    Lưu bản nháp
                  </button>

                  <button
                    type="submit"
                    disabled={isSubmitting}
                    className="flex items-center gap-2 px-6 py-2.5 text-xs font-bold text-white bg-emerald-700 hover:bg-emerald-800 active:bg-emerald-800 rounded-xl shadow-md shadow-emerald-600/20 transition-all cursor-pointer disabled:opacity-50"
                  >
                    {isSubmitting ? (
                      <>
                        <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                        <span>Đang tạo hồ sơ mẫu...</span>
                      </>
                    ) : (
                      <>
                        <Send size={15} />
                        <span>Thêm hồ sơ đăng ký mẫu</span>
                      </>
                    )}
                  </button>
                </div>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* TAB 5: BỆNH VIỆN & TRƯỜNG HỌC */}
      {activeTab === 'hospital_school' && (
        <div className="space-y-6">
          {/* Hospitals */}
          <div className="space-y-4">
            <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
              <HeartPulse size={18} className="text-rose-600" />
              <span>Hệ thống Cơ sở Y tế & Chăm sóc Sức khỏe Đô thị</span>
            </h3>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {amenitiesData.hospitals.map((hosp) => (
                <div key={hosp.id} className="bg-white rounded-2xl border border-slate-200/90 shadow-xs overflow-hidden flex flex-col justify-between">
                  <div className="relative h-44">
                    <PreviewImage src={hosp.image} alt={hosp.name} className="w-full h-full object-cover" />
                    <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/20 to-transparent" />
                    <div className="absolute bottom-3 left-4 right-4 text-white">
                      <span className="text-xs bg-rose-600 text-white font-bold px-2 py-0.5 rounded">
                        {hosp.badge}
                      </span>
                      <h4 className="text-base font-bold mt-1">{hosp.name}</h4>
                      <p className="text-xs text-slate-200 mt-0.5">{hosp.scale}</p>
                    </div>
                  </div>

                  <div className="p-4 space-y-3 text-xs">
                    <div className="space-y-1">
                      <p className="text-slate-600 flex items-center gap-1.5">
                        <MapPin size={13} className="text-slate-400" />
                        <span>{hosp.location}</span>
                      </p>
                      <p className="text-slate-600 flex items-center gap-1.5">
                        <Phone size={13} className="text-rose-600 font-bold" />
                        <span>Hotline: <strong className="text-rose-600">{hosp.hotline}</strong></span>
                      </p>
                    </div>

                    <div className="pt-2 border-t border-slate-100">
                      <span className="text-xs font-bold text-slate-700">Dịch vụ trọng điểm:</span>
                      <div className="flex flex-wrap gap-1.5 mt-1.5">
                        {hosp.services.map((srv, idx) => (
                          <span key={idx} className="text-xs bg-rose-50 text-rose-800 font-medium px-2 py-0.5 rounded border border-rose-200/60">
                            {srv}
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Schools */}
          <div className="space-y-4 pt-4 border-t border-slate-200">
            <h3 className="text-base font-bold text-slate-900 flex items-center gap-2">
              <GraduationCap size={18} className="text-indigo-600" />
              <span>Hệ thống Giáo dục & Trường học Chuẩn Quốc tế</span>
            </h3>

            <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
              {amenitiesData.schools.map((sch) => (
                <div key={sch.id} className="bg-white rounded-2xl border border-slate-200/90 shadow-xs overflow-hidden flex flex-col justify-between">
                  <div className="relative h-44">
                    <PreviewImage src={sch.image} alt={sch.name} className="w-full h-full object-cover" />
                    <div className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/20 to-transparent" />
                    <div className="absolute bottom-3 left-4 right-4 text-white">
                      <span className="text-xs bg-indigo-600 text-white font-bold px-2 py-0.5 rounded">
                        {sch.badge}
                      </span>
                      <h4 className="text-base font-bold mt-1">{sch.name}</h4>
                      <p className="text-xs text-slate-200 mt-0.5">{sch.levels} • Quy mô: {sch.studentsCount}</p>
                    </div>
                  </div>

                  <div className="p-4 space-y-3 text-xs">
                    <div className="space-y-1">
                      <p className="text-slate-600 flex items-center gap-1.5">
                        <MapPin size={13} className="text-slate-400" />
                        <span>{sch.location}</span>
                      </p>
                      <p className="text-slate-600 flex items-center gap-1.5">
                        <Phone size={13} className="text-indigo-600 font-bold" />
                        <span>Tư vấn tuyển sinh: <strong className="text-indigo-600">{sch.hotline}</strong></span>
                      </p>
                    </div>

                    <div className="pt-2 border-t border-slate-100">
                      <span className="text-xs font-bold text-slate-700">Điểm nổi bật:</span>
                      <div className="flex flex-wrap gap-1.5 mt-1.5">
                        {sch.highlights.map((hl, idx) => (
                          <span key={idx} className="text-xs bg-indigo-50 text-indigo-800 font-medium px-2 py-0.5 rounded border border-indigo-200/60">
                            {hl}
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
      <Dialog open={Boolean(selectedRegistration)} onClose={() => setSelectedRegistration(null)} title="Hồ sơ đăng ký gian hàng mẫu">
        {selectedRegistration && <div className="dialog-body"><h3 className="task-detail-title">{selectedRegistration.brandName}</h3><dl className="confirmation-details"><div><dt>Người đại diện</dt><dd>{selectedRegistration.representative}</dd></div><div><dt>Ngành hàng</dt><dd>{selectedRegistration.category}</dd></div><div><dt>Vị trí đề nghị</dt><dd>{selectedRegistration.desiredLocation}</dd></div><div><dt>Thời hạn thuê</dt><dd>{selectedRegistration.leaseDuration}</dd></div><div><dt>Trạng thái mẫu</dt><dd>{selectedRegistration.status}</dd></div><div><dt>Hồ sơ kèm theo</dt><dd>{selectedRegistration.businessLicense}</dd></div></dl><p className="context-note">Chỉ xem hồ sơ mẫu; chưa thẩm định hoặc phê duyệt hồ sơ thật.</p></div>}
      </Dialog>
    </div>
  );
};
