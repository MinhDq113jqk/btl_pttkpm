import React, { useState } from 'react';
import { 
  Globe, 
  Share2, 
  MessageSquare, 
  ThumbsUp, 
  Eye, 
  Calendar, 
  Clock, 
  CheckCircle2, 
  AlertCircle, 
  Plus, 
  ExternalLink, 
  Image as ImageIcon, 
  UploadCloud, 
  Sparkles, 
  Send, 
  FileText, 
  ShieldCheck, 
  Sliders, 
  Radio, 
  Check, 
  ArrowRight,
  TrendingUp,
  Activity,
  Layers
} from 'lucide-react';
import { mediaData } from '../data/mockData';
import { Dialog } from './Dialog';
import { PreviewImage } from './PreviewImage';

export const MediaChannelsView = ({ onOpenServiceRequest, onToast }) => {
  const [activeSubTab, setActiveSubTab] = useState('overview'); // 'overview' | 'facebook' | 'website' | 'compose'

  // Post composer state
  const [composerData, setComposerData] = useState({
    title: '',
    category: 'Thông báo BQL',
    content: '',
    publishFb: true,
    publishWeb: true,
    scheduleType: 'now', // 'now' | 'scheduled'
    scheduleTime: '2026-09-08T09:00',
    imageUrl: ''
  });

  const [postsList, setPostsList] = useState(mediaData.facebook.posts);
  const [bannersList, setBannersList] = useState(mediaData.website.banners);
  const [isPublishing, setIsPublishing] = useState(false);
  const [selectedPost, setSelectedPost] = useState(null);
  const [savedComposer, setSavedComposer] = useState(null);
  const [composeError, setComposeError] = useState('');

  const handleToggleBanner = (id) => {
    setBannersList(prev => prev.map(b => b.id === id ? { ...b, active: !b.active } : b));
    onToast?.('Đã đổi trạng thái banner trong bản mô phỏng, chưa cập nhật website thật.', 'info');
  };

  const handlePublishPost = (e) => {
    e.preventDefault();
    if (isPublishing) return;
    setComposeError('');
    if (!composerData.publishFb && !composerData.publishWeb) {
      setComposeError('Chọn ít nhất một kênh đăng bài.');
      return;
    }
    if (composerData.scheduleType === 'scheduled' && (!composerData.scheduleTime || new Date(composerData.scheduleTime).getTime() <= Date.now())) {
      setComposeError('Chọn thời điểm lên lịch trong tương lai. Bản mô phỏng không tự đăng khi đến giờ.');
      return;
    }
    if (!composerData.title.trim() || !composerData.content.trim()) {
      onToast?.('Vui lòng nhập đầy đủ tiêu đề và nội dung bài viết.', 'warning');
      return;
    }

    setIsPublishing(true);
    setTimeout(() => {
      const newPost = {
        id: `fb-${Date.now()}`,
        title: composerData.title,
        date: composerData.scheduleType === 'now' ? 'Vừa xong' : `Lên lịch: ${composerData.scheduleTime.replace('T', ' ')}`,
        reach: 0,
        likes: 0,
        comments: 0,
        shares: 0,
        status: composerData.scheduleType === 'now' ? 'Bài mô phỏng' : 'Lịch đăng mô phỏng',
        content: composerData.content,
        channels: [composerData.publishFb && 'Facebook', composerData.publishWeb && 'Website'].filter(Boolean).join(', '),
        image: composerData.imageUrl || 'https://images.unsplash.com/photo-1545324418-cc1a3fa10c00?auto=format&fit=crop&w=600&q=80'
      };

      setPostsList([newPost, ...postsList]);
      setIsPublishing(false);
      onToast?.('Đã thêm bài vào danh sách mô phỏng. Chưa đăng lên Facebook hoặc Website.', 'info');
      setSavedComposer(null);
      
      // Reset composer
      setComposerData({
        title: '',
        category: 'Thông báo BQL',
        content: '',
        publishFb: true,
        publishWeb: true,
        scheduleType: 'now',
        scheduleTime: '2026-09-08T09:00',
        imageUrl: ''
      });
      setActiveSubTab('facebook');
    }, 1000);
  };

  return (
    <div className="p-4 sm:p-8 max-w-7xl mx-auto space-y-6 pb-24">
      {/* Page Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wider text-emerald-700">
            <span>GREENCITY</span>
            <span>/</span>
            <span className="text-slate-400">TRUYỀN THÔNG & KÊNH SỐ</span>
          </div>
          <h1 className="text-2xl font-bold text-slate-900 mt-1">
            Quản lý Fanpage Facebook & Website Đô thị
          </h1>
          <p className="text-xs text-slate-500 mt-0.5">
            Hệ thống xuất bản tin tức, đồng bộ thông báo cư dân và kiểm soát hiện diện số của GreenCity.
          </p>
        </div>

        {/* Action Button: Soạn bài mới */}
        <div className="flex items-center gap-2">
          <button
            onClick={() => setActiveSubTab('compose')}
            className="flex items-center gap-2 px-4 py-2.5 bg-emerald-700 hover:bg-emerald-800 active:bg-emerald-800 text-white rounded-xl text-xs font-bold shadow-sm shadow-emerald-600/20 transition-all cursor-pointer"
          >
            <Plus size={16} />
            <span>Soạn & Đăng bài mới</span>
          </button>
        </div>
      </div>

      {/* Sub-Navigation Tabs */}
      <div className="flex items-center gap-2 border-b border-slate-200 overflow-x-auto pb-1 text-xs">
        <button
          onClick={() => setActiveSubTab('overview')}
          className={`px-4 py-2.5 rounded-xl font-bold transition-all flex items-center gap-2 ${
            activeSubTab === 'overview'
              ? 'bg-emerald-50 text-emerald-700 shadow-2xs border border-emerald-200'
              : 'text-slate-600 hover:bg-slate-50'
          }`}
        >
          <Activity size={15} />
          <span>Tổng quan 2 kênh</span>
        </button>

        <button
          onClick={() => setActiveSubTab('facebook')}
          className={`px-4 py-2.5 rounded-xl font-bold transition-all flex items-center gap-2 ${
            activeSubTab === 'facebook'
              ? 'bg-blue-50 text-blue-700 shadow-2xs border border-blue-200'
              : 'text-slate-600 hover:bg-slate-50'
          }`}
        >
          <div className="w-4 h-4 rounded-full bg-blue-600 text-white flex items-center justify-center font-bold text-xs">
            f
          </div>
          <span>Fanpage Facebook</span>
          <span className="text-xs bg-blue-100 text-blue-800 px-1.5 py-0.2 rounded-full font-bold">
            48.5K
          </span>
        </button>

        <button
          onClick={() => setActiveSubTab('website')}
          className={`px-4 py-2.5 rounded-xl font-bold transition-all flex items-center gap-2 ${
            activeSubTab === 'website'
              ? 'bg-teal-50 text-teal-700 shadow-2xs border border-teal-200'
              : 'text-slate-600 hover:bg-slate-50'
          }`}
        >
          <Globe size={15} className="text-teal-600" />
          <span>Website greencity.vn</span>
          <span className="text-xs bg-teal-100 text-teal-800 px-1.5 py-0.2 rounded-full font-bold">
            Mẫu
          </span>
        </button>

        <button
          onClick={() => setActiveSubTab('compose')}
          className={`px-4 py-2.5 rounded-xl font-bold transition-all flex items-center gap-2 ${
            activeSubTab === 'compose'
              ? 'bg-slate-900 text-white shadow-2xs'
              : 'text-slate-600 hover:bg-slate-50'
          }`}
        >
          <Plus size={15} />
          <span>Soạn bài đăng đa kênh</span>
        </button>
      </div>

      {/* TAB 1: OVERVIEW BOTH CHANNELS */}
      {activeSubTab === 'overview' && (
        <div className="space-y-6">
          {/* 2 Channel Big Status Cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Facebook Quick Card */}
            <div className="bg-white rounded-2xl border border-slate-200/90 shadow-xs p-6 space-y-4 hover:border-blue-300 transition-all">
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-12 h-12 rounded-2xl bg-blue-600 text-white flex items-center justify-center font-bold text-2xl shadow-md shadow-blue-500/20">
                    f
                  </div>
                  <div>
                    <div className="flex items-center gap-1.5">
                      <h3 className="text-sm font-bold text-slate-900">GreenCity Urban Official</h3>
                      <CheckCircle2 size={15} className="text-blue-500 fill-blue-500 text-white" />
                    </div>
                    <p className="text-xs text-slate-400">@greencity.official • Meta Verified</p>
                  </div>
                </div>

                <span className="px-2.5 py-1 rounded-full bg-blue-50 text-blue-700 text-xs font-bold border border-blue-200">
                  ● Meta API Active
                </span>
              </div>

              <div className="grid grid-cols-3 gap-2 pt-2 border-t border-slate-100 text-center">
                <div className="p-2.5 rounded-xl bg-slate-50">
                  <span className="text-xs text-slate-400 font-medium">Người theo dõi</span>
                  <p className="text-base font-bold text-slate-900 mt-0.5">{mediaData.facebook.followers}</p>
                </div>
                <div className="p-2.5 rounded-xl bg-slate-50">
                  <span className="text-xs text-slate-400 font-medium">Tiếp cận 28 ngày</span>
                  <p className="text-base font-bold text-blue-600 mt-0.5">{mediaData.facebook.reachThisMonth}</p>
                </div>
                <div className="p-2.5 rounded-xl bg-slate-50">
                  <span className="text-xs text-slate-400 font-medium">Tin nhắn chờ</span>
                  <p className="text-base font-bold text-amber-600 mt-0.5">{mediaData.facebook.inbox.filter(message => message.unread).length}</p>
                </div>
              </div>

              <div className="flex items-center justify-between pt-2">
                <button
                  onClick={() => setActiveSubTab('facebook')}
                  className="text-xs font-bold text-blue-600 hover:text-blue-700 flex items-center gap-1"
                >
                  <span>Quản lý Fanpage & Hộp thư</span>
                  <ArrowRight size={14} />
                </button>
                <a
                  href="https://facebook.com"
                  target="_blank"
                  rel="noreferrer"
                  className="p-2 rounded-xl text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
                  title="Mở Fanpage trên Facebook"
                >
                  <ExternalLink size={16} />
                </a>
              </div>
            </div>

            {/* Website Quick Card */}
            <div className="bg-white rounded-2xl border border-slate-200/90 shadow-xs p-6 space-y-4 hover:border-emerald-300 transition-all">
              <div className="flex items-start justify-between">
                <div className="flex items-center gap-3">
                  <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-emerald-500 to-teal-700 text-white flex items-center justify-center shadow-md shadow-emerald-500/20">
                    <Globe size={24} />
                  </div>
                  <div>
                    <div className="flex items-center gap-1.5">
                      <h3 className="text-sm font-bold text-slate-900">greencity.vn</h3>
                      <ShieldCheck size={15} className="text-emerald-700" />
                    </div>
                    <p className="text-xs text-slate-400">Cổng Thông tin & Dịch vụ Trực tuyến</p>
                  </div>
                </div>

                <span className="px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-700 text-xs font-bold border border-emerald-200">
                  Website mẫu
                </span>
              </div>

              <div className="grid grid-cols-3 gap-2 pt-2 border-t border-slate-100 text-center">
                <div className="p-2.5 rounded-xl bg-slate-50">
                  <span className="text-xs text-slate-400 font-medium">Lượt xem tháng</span>
                  <p className="text-base font-bold text-slate-900 mt-0.5">{mediaData.website.monthlyVisits}</p>
                </div>
                <div className="p-2.5 rounded-xl bg-slate-50">
                  <span className="text-xs text-slate-400 font-medium">Người dùng mới</span>
                  <p className="text-base font-bold text-emerald-700 mt-0.5">{mediaData.website.uniqueVisitors}</p>
                </div>
                <div className="p-2.5 rounded-xl bg-slate-50">
                  <span className="text-xs text-slate-400 font-medium">Điểm SEO / Tốc độ</span>
                  <p className="text-base font-bold text-teal-700 mt-0.5">{mediaData.website.seoScore}</p>
                </div>
              </div>

              <div className="flex items-center justify-between pt-2">
                <button
                  onClick={() => setActiveSubTab('website')}
                  className="text-xs font-bold text-emerald-700 hover:text-emerald-800 flex items-center gap-1"
                >
                  <span>Quản lý Banners & Tin tức</span>
                  <ArrowRight size={14} />
                </button>
                <a
                  href="https://greencity.vn"
                  target="_blank"
                  rel="noreferrer"
                  className="p-2 rounded-xl text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors"
                  title="Mở website greencity.vn"
                >
                  <ExternalLink size={16} />
                </a>
              </div>
            </div>
          </div>

          {/* Cross-channel Recent Activity stream */}
          <div className="bg-white rounded-2xl border border-slate-200/90 shadow-xs p-6 space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div>
                <h3 className="text-base font-bold text-slate-900">Bài đăng & Hoạt động truyền thông mới nhất</h3>
                <p className="text-xs text-slate-400 mt-0.5">Xuất bản đồng bộ trên Fanpage Facebook và Cổng thông tin Website</p>
              </div>
              <button
                onClick={() => setActiveSubTab('compose')}
                className="text-xs font-bold text-emerald-700 hover:underline flex items-center gap-1"
              >
                <span>+ Soạn bài mới</span>
              </button>
            </div>

            <div className="divide-y divide-slate-100">
              {postsList.map((post) => (
                <div key={post.id} className="py-4 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
                  <div className="flex items-start gap-3.5">
                    <PreviewImage
                      src={post.image}
                      alt={post.title}
                      className="w-14 h-14 rounded-xl object-cover border border-slate-200 flex-shrink-0"
                    />
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <span className="text-xs bg-blue-50 text-blue-700 font-bold px-2 py-0.5 rounded border border-blue-200">
                          Facebook
                        </span>
                        <span className="text-xs bg-emerald-50 text-emerald-700 font-bold px-2 py-0.5 rounded border border-emerald-200">
                          Website
                        </span>
                        <span className="text-xs text-slate-400">{post.date}</span>
                      </div>
                      <h4 className="text-xs font-bold text-slate-900 line-clamp-1">{post.title}</h4>
                      <div className="flex items-center gap-4 text-xs text-slate-500">
                        <span className="flex items-center gap-1">
                          <Eye size={12} className="text-slate-400" />
                          <span>{post.reach.toLocaleString()} tiếp cận</span>
                        </span>
                        <span className="flex items-center gap-1">
                          <ThumbsUp size={12} className="text-slate-400" />
                          <span>{post.likes} thích</span>
                        </span>
                        <span className="flex items-center gap-1">
                          <MessageSquare size={12} className="text-slate-400" />
                          <span>{post.comments} bình luận</span>
                        </span>
                      </div>
                    </div>
                  </div>

                  <div className="flex items-center gap-2 self-end sm:self-center">
                    <span className="text-xs px-2.5 py-1 rounded-full font-bold bg-emerald-100 text-emerald-800">
                      {post.status}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: FACEBOOK FANPAGE MANAGEMENT */}
      {activeSubTab === 'facebook' && (
        <div className="space-y-6">
          {/* Fanpage Header Banner */}
          <div className="rounded-3xl bg-gradient-to-r from-blue-700 via-blue-800 to-indigo-900 p-6 text-white shadow-lg relative overflow-hidden">
            <div className="relative z-10 flex flex-col md:flex-row md:items-center justify-between gap-6">
              <div className="flex items-center gap-4">
                <div className="w-16 h-16 rounded-2xl bg-white text-blue-600 flex items-center justify-center font-bold text-3xl shadow-md flex-shrink-0">
                  f
                </div>
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <h2 className="text-xl font-bold">{mediaData.facebook.pageName}</h2>
                    <CheckCircle2 size={18} className="text-blue-300 fill-blue-300 text-blue-800" />
                  </div>
                  <p className="text-xs text-blue-200">
                    {mediaData.facebook.handle} • {mediaData.facebook.followers} người theo dõi • Đánh giá: {mediaData.facebook.rating}
                  </p>
                  <p className="text-xs text-blue-100/80">
                    {mediaData.facebook.connectionStatus} ({mediaData.facebook.tokenExpiry})
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-3">
                <button
                  onClick={() => setActiveSubTab('compose')}
                  className="px-4 py-2 rounded-xl bg-white text-blue-700 font-bold text-xs hover:bg-blue-50 transition-colors shadow-sm"
                >
                  + Đăng bài lên Fanpage
                </button>
              </div>
            </div>
          </div>

          {/* Facebook In-depth Grid: Posts vs Messenger Inbox */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Posts Stream (2 cols) */}
            <div className="lg:col-span-2 bg-white rounded-2xl border border-slate-200/90 shadow-xs p-6 space-y-4">
              <div className="flex items-center justify-between pb-3 border-b border-slate-100">
                <h3 className="text-sm font-bold text-slate-900">Danh sách bài đăng trên Trang</h3>
                <span className="text-xs text-slate-400 font-medium">Danh sách minh họa · Chưa đồng bộ</span>
              </div>

              <div className="space-y-4">
                {postsList.map((post) => (
                  <div key={post.id} className="p-4 rounded-xl border border-slate-200 bg-slate-50/50 hover:bg-white hover:border-slate-300 transition-all space-y-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="flex items-start gap-3">
                        <PreviewImage
                          src={post.image}
                          alt={post.title}
                          className="w-16 h-16 rounded-xl object-cover border border-slate-200 flex-shrink-0"
                        />
                        <div className="space-y-1">
                          <span className="text-xs text-slate-400 font-medium">{post.date}</span>
                          <h4 className="text-xs font-bold text-slate-900 leading-snug">{post.title}</h4>
                        </div>
                      </div>
                      <span className={`text-xs px-2.5 py-0.5 rounded-full font-bold whitespace-nowrap ${
                        post.status === 'Đã xuất bản' ? 'bg-emerald-100 text-emerald-800' : 'bg-blue-100 text-blue-800'
                      }`}>
                        {post.status}
                      </span>
                    </div>

                    <div className="flex items-center justify-between text-xs text-slate-500 pt-2 border-t border-slate-200/60">
                      <div className="flex items-center gap-4 text-xs">
                        <span><strong>{post.reach.toLocaleString()}</strong> tiếp cận</span>
                        <span><strong>{post.likes}</strong> thích</span>
                        <span><strong>{post.comments}</strong> bình luận</span>
                        <span><strong>{post.shares}</strong> chia sẻ</span>
                      </div>
                      <button onClick={() => setSelectedPost(post)} className="text-blue-600 hover:text-blue-700 font-semibold text-xs">
                        Xem chi tiết →
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* Messenger Inbox Sync (1 col) */}
            <div className="bg-white rounded-2xl border border-slate-200/90 shadow-xs p-6 space-y-4">
              <div className="flex items-center justify-between pb-3 border-b border-slate-100">
                <div className="flex items-center gap-2">
                  <MessageSquare size={16} className="text-blue-600" />
                  <h3 className="text-sm font-bold text-slate-900">Tin nhắn Messenger ({mediaData.facebook.unreadMessages})</h3>
                </div>
                <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
              </div>

              <div className="space-y-3">
                {mediaData.facebook.inbox.map((msg) => (
                  <div 
                    key={msg.id}
                    className={`p-3 rounded-xl border transition-all space-y-2 ${
                      msg.unread ? 'bg-blue-50/40 border-blue-200' : 'bg-slate-50/70 border-slate-200'
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <div className="w-7 h-7 rounded-full bg-blue-600 text-white font-bold text-xs flex items-center justify-center">
                          {msg.avatar}
                        </div>
                        <span className="text-xs font-bold text-slate-800">{msg.sender}</span>
                      </div>
                      <span className="text-xs text-slate-400">{msg.time}</span>
                    </div>

                    <p className="text-xs text-slate-600 leading-snug">
                      "{msg.preview}"
                    </p>

                    <div className="flex items-center justify-end gap-2 pt-1">
                      <button
                        onClick={() => onOpenServiceRequest?.(msg)}
                        className="text-xs font-bold text-emerald-700 hover:bg-emerald-50 px-2 py-1 rounded-lg border border-emerald-300 transition-colors"
                      >
                        + Tạo phiếu yêu cầu BQL
                      </button>
                      <button disabled title="Chưa kết nối Messenger" className="text-xs font-bold text-blue-700 px-2 py-1 rounded-lg">
                        Trả lời (chưa kết nối)
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TAB 3: WEBSITE MANAGEMENT (greencity.vn) */}
      {activeSubTab === 'website' && (
        <div className="space-y-6">
          {/* Website Domain & Performance Banner */}
          <div className="rounded-3xl bg-gradient-to-r from-emerald-800 via-teal-900 to-slate-900 p-6 text-white shadow-lg">
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
              <div className="space-y-1.5">
                <div className="flex items-center gap-2">
                  <Globe size={20} className="text-emerald-400" />
                  <h2 className="text-xl font-bold">{mediaData.website.domain}</h2>
                  <span className="px-2 py-0.5 rounded-full bg-emerald-400/20 text-emerald-300 text-xs font-bold border border-emerald-400/30">
                    {mediaData.website.sslStatus}
                  </span>
                </div>
                <p className="text-xs text-slate-300">{mediaData.website.title}</p>
                <p className="text-xs text-slate-400">
                  Uptime: {mediaData.website.uptime} • CDN: Cloudflare Enterprise • Hosting: Dedicated Server Hà Nội
                </p>
              </div>

              <div className="flex items-center gap-3">
                <a
                  href="https://greencity.vn"
                  target="_blank"
                  rel="noreferrer"
                  className="px-4 py-2 rounded-xl bg-white text-emerald-900 font-bold text-xs hover:bg-slate-100 transition-colors flex items-center gap-1.5 shadow-sm"
                >
                  <span>Xem Website Cư dân</span>
                  <ExternalLink size={14} />
                </a>
              </div>
            </div>
          </div>

          {/* Banner Slider Manager */}
          <div className="bg-white rounded-2xl border border-slate-200/90 shadow-xs p-6 space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div>
                <h3 className="text-base font-bold text-slate-900">Quản lý Banner Slider Trang chủ</h3>
                <p className="text-xs text-slate-400 mt-0.5">Banner kích hoạt sẽ hiển thị trên đầu website greencity.vn</p>
              </div>
              <button 
                onClick={() => onToast?.('Chức năng thêm banner chưa triển khai. Bạn có thể thử bật/tắt các banner mẫu bên dưới.', 'info')}
                className="text-xs font-bold text-emerald-700 hover:underline flex items-center gap-1"
              >
                <Plus size={14} />
                <span>Thêm banner mới</span>
              </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              {bannersList.map((banner) => (
                <div key={banner.id} className="rounded-xl border border-slate-200 overflow-hidden bg-slate-50 flex flex-col justify-between">
                  <div className="relative">
                    <PreviewImage src={banner.image} alt={banner.title} className="w-full h-32 object-cover" />
                    <span className="absolute top-2 left-2 px-2 py-0.5 rounded-md bg-black/60 text-white text-xs font-semibold backdrop-blur-xs">
                      {banner.tag}
                    </span>
                  </div>

                  <div className="p-3 space-y-2 flex-1 flex flex-col justify-between">
                    <h4 className="text-xs font-bold text-slate-800 leading-snug line-clamp-2">
                      {banner.title}
                    </h4>

                    <div className="flex items-center justify-between pt-2 border-t border-slate-200/60">
                      <span className={`text-xs font-bold ${banner.active ? 'text-emerald-700' : 'text-slate-400'}`}>
                        {banner.active ? '● Đang hiển thị' : '○ Tạm ẩn'}
                      </span>
                      <button
                        onClick={() => handleToggleBanner(banner.id)}
                        className={`text-xs px-2 py-1 rounded-lg font-bold border transition-colors ${
                          banner.active 
                            ? 'bg-rose-50 text-rose-700 border-rose-200 hover:bg-rose-100' 
                            : 'bg-emerald-50 text-emerald-700 border-emerald-200 hover:bg-emerald-100'
                        }`}
                      >
                        {banner.active ? 'Tạm ẩn' : 'Bật hiển thị'}
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Website Articles & Online Submissions */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Articles List */}
            <div className="bg-white rounded-2xl border border-slate-200/90 shadow-xs p-6 space-y-4">
              <div className="flex items-center justify-between pb-3 border-b border-slate-100">
                <h3 className="text-sm font-bold text-slate-900">Tin tức & Văn bản BQL</h3>
                <span className="text-xs text-slate-400 font-medium">{mediaData.website.articles.length} bài viết</span>
              </div>

              <div className="space-y-3">
                {mediaData.website.articles.map((art) => (
                  <div key={art.id} className="p-3 rounded-xl border border-slate-200/80 bg-slate-50/50 hover:bg-white transition-colors flex items-center justify-between gap-3">
                    <div className="space-y-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-xs bg-slate-100 text-slate-700 font-bold px-2 py-0.5 rounded">
                          {art.category}
                        </span>
                        <span className="text-xs text-slate-400">{art.publishedDate}</span>
                      </div>
                      <h4 className="text-xs font-bold text-slate-900 truncate">{art.title}</h4>
                      <p className="text-xs text-slate-400 flex items-center gap-1">
                        <Eye size={12} />
                        <span>{art.views.toLocaleString()} lượt đọc</span>
                      </p>
                    </div>
                    <span className="text-xs px-2 py-0.5 rounded-full font-bold bg-emerald-100 text-emerald-800 whitespace-nowrap">
                      {art.status}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {/* Online Resident Submissions */}
            <div className="bg-white rounded-2xl border border-slate-200/90 shadow-xs p-6 space-y-4">
              <div className="flex items-center justify-between pb-3 border-b border-slate-100">
                <h3 className="text-sm font-bold text-slate-900">Hồ sơ Cư dân gửi từ Website</h3>
                <span className="text-xs text-emerald-700 font-bold">2 hồ sơ mới</span>
              </div>

              <div className="space-y-3">
                {mediaData.website.onlineSubmissions.map((sub) => (
                  <div key={sub.id} className="p-3.5 rounded-xl border border-slate-200 bg-slate-50/60 hover:bg-white transition-colors space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-slate-900">{sub.formType}</span>
                      <span className={`text-xs px-2 py-0.5 rounded-md font-bold ${
                        sub.status === 'Đã phê duyệt' ? 'bg-emerald-100 text-emerald-800' : 'bg-amber-100 text-amber-800'
                      }`}>
                        {sub.status}
                      </span>
                    </div>
                    <div className="flex items-center justify-between text-xs text-slate-500">
                      <span>Người nộp: <strong>{sub.resident}</strong></span>
                      <span>{sub.date}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TAB 4: MULTI-CHANNEL POST COMPOSER */}
      {activeSubTab === 'compose' && (
        <div className="bg-white rounded-2xl border border-slate-200/90 shadow-xs p-6 space-y-6">
          <div className="pb-4 border-b border-slate-100">
            <h2 className="text-lg font-bold text-slate-900">Soạn bài & Đăng đồng bộ đa kênh</h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Soạn và thử thêm bài vào danh sách mẫu. Chưa đăng lên Facebook hoặc Website. Dữ liệu mất khi tải lại ứng dụng.
            </p>
          </div>

          <form onSubmit={handlePublishPost} className="space-y-6">
            {savedComposer && <button type="button" className="button-secondary" onClick={() => { setComposerData({ ...savedComposer }); setComposeError(''); }}>Khôi phục nháp bài viết trong phiên</button>}
            {composeError && <p className="field-error" role="alert">{composeError}</p>}
            {/* Target Channels */}
            <div className="space-y-2">
              <label className="text-xs font-bold text-slate-700">Kênh đăng bài mục tiêu</label>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <label className={`flex items-center gap-3 p-3 rounded-xl border cursor-pointer transition-all ${
                  composerData.publishFb 
                    ? 'border-blue-500 bg-blue-50/40 text-blue-900 ring-1 ring-blue-500' 
                    : 'border-slate-200 bg-slate-50'
                }`}>
                  <input
                    type="checkbox"
                    checked={composerData.publishFb}
                    onChange={(e) => setComposerData({ ...composerData, publishFb: e.target.checked })}
                    className="rounded text-blue-600 focus:ring-blue-500"
                  />
                  <div className="text-xs">
                    <p className="font-bold">Fanpage Facebook (@greencity.official)</p>
                    <p className="text-xs text-slate-500">Đăng dạng Post chính thức kèm ảnh</p>
                  </div>
                </label>

                <label className={`flex items-center gap-3 p-3 rounded-xl border cursor-pointer transition-all ${
                  composerData.publishWeb 
                    ? 'border-emerald-500 bg-emerald-50/40 text-emerald-900 ring-1 ring-emerald-500' 
                    : 'border-slate-200 bg-slate-50'
                }`}>
                  <input
                    type="checkbox"
                    checked={composerData.publishWeb}
                    onChange={(e) => setComposerData({ ...composerData, publishWeb: e.target.checked })}
                    className="rounded text-emerald-700 focus:ring-emerald-500"
                  />
                  <div className="text-xs">
                    <p className="font-bold">Cổng Website BQL (greencity.vn)</p>
                    <p className="text-xs text-slate-500">Xuất bản vào mục Thông báo & Tin tức</p>
                  </div>
                </label>
              </div>
            </div>

            {/* Title & Category */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs">
              <div className="sm:col-span-2 space-y-1.5">
                <label htmlFor="media-title" className="font-bold text-slate-700">Tiêu đề thông báo / bài viết *</label>
                <input
                  type="text"
                  required
                  id="media-title"
                    value={composerData.title}
                  onChange={(e) => setComposerData({ ...composerData, title: e.target.value })}
                  placeholder="Ví dụ: Thông báo kiểm tra hệ thống PCCC tháp Grand Park B..."
                  className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500/20 outline-none font-medium text-slate-800"
                />
              </div>

              <div className="space-y-1.5">
                <label htmlFor="media-category" className="font-bold text-slate-700">Chuyên mục</label>
                <select
                  id="media-category"
                    value={composerData.category}
                  onChange={(e) => setComposerData({ ...composerData, category: e.target.value })}
                  className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500/20 outline-none font-medium text-slate-800 bg-white"
                >
                  <option>Thông báo BQL</option>
                  <option>Lịch bảo trì kỹ thuật</option>
                  <option>Sự kiện cư dân</option>
                  <option>Hướng dẫn & Quy chế</option>
                  <option>Tin môi trường xanh</option>
                </select>
              </div>
            </div>

            {/* Post Content Body */}
            <div className="space-y-1.5 text-xs">
              <label htmlFor="media-content" className="font-bold text-slate-700">Nội dung chi tiết *</label>
              <textarea
                rows={5}
                required
                id="media-content"
                    value={composerData.content}
                onChange={(e) => setComposerData({ ...composerData, content: e.target.value })}
                placeholder="Nhập nội dung bài viết gửi tới toàn thể quý cư dân khu đô thị..."
                className="w-full p-3.5 rounded-xl border border-slate-200 focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500/20 outline-none text-slate-800 resize-none font-normal"
              />
            </div>

            {/* Image URL / Dropzone */}
            <div className="space-y-1.5 text-xs">
              <label htmlFor="media-imageUrl" className="font-bold text-slate-700">Hình ảnh minh họa / Poster (Tùy chọn)</label>
              <input
                type="text"
                id="media-imageUrl"
                    value={composerData.imageUrl}
                onChange={(e) => setComposerData({ ...composerData, imageUrl: e.target.value })}
                placeholder="Dán link ảnh hoặc để trống hệ thống sẽ lấy ảnh mặc định chuẩn thương hiệu GreenCity"
                className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 focus:border-emerald-500 focus:ring-2 focus:ring-emerald-500/20 outline-none text-slate-700"
              />
            </div>

            {/* Schedule options */}
            <div className="space-y-2 text-xs pt-2 border-t border-slate-100">
              <label className="font-bold text-slate-700">Thời điểm đăng</label>
              <div className="flex items-center gap-6">
                <label className="flex items-center gap-2 cursor-pointer font-medium text-slate-700">
                  <input
                    type="radio"
                    name="scheduleType"
                    value="now"
                    checked={composerData.scheduleType === 'now'}
                    onChange={() => setComposerData({ ...composerData, scheduleType: 'now' })}
                    className="text-emerald-700 focus:ring-emerald-500"
                  />
                  <span>Đăng ngay lập tức</span>
                </label>

                <label className="flex items-center gap-2 cursor-pointer font-medium text-slate-700">
                  <input
                    type="radio"
                    name="scheduleType"
                    value="scheduled"
                    checked={composerData.scheduleType === 'scheduled'}
                    onChange={() => setComposerData({ ...composerData, scheduleType: 'scheduled' })}
                    className="text-emerald-700 focus:ring-emerald-500"
                  />
                  <span>Hẹn giờ lên lịch đăng</span>
                </label>

                {composerData.scheduleType === 'scheduled' && (
                  <input
                    type="datetime-local"
                    aria-label="Thời điểm lên lịch đăng"
                    required
                    value={composerData.scheduleTime}
                    onChange={(e) => setComposerData({ ...composerData, scheduleTime: e.target.value })}
                    className="px-3 py-1.5 rounded-lg border border-slate-200 text-xs text-slate-800"
                  />
                )}
              </div>
            </div>

            {/* Mistake-proof Action Buttons */}
            <div className="flex items-center justify-between pt-4 border-t border-slate-100">
              <button
                type="button"
                onClick={() => setActiveSubTab('overview')}
                className="px-4 py-2.5 text-xs font-semibold text-slate-600 hover:text-slate-900 rounded-xl border border-slate-200 hover:bg-slate-100 transition-colors"
              >
                Về tổng quan
              </button>

              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={() => { setSavedComposer({ ...composerData }); onToast?.('Đã lưu nháp bài viết trong phiên này. Tải lại ứng dụng sẽ xóa bản nháp.', 'info'); }}
                  className="px-4 py-2.5 text-xs font-semibold text-slate-700 bg-slate-50 border border-slate-300 rounded-xl hover:bg-slate-100 transition-colors"
                >
                  Lưu bản nháp
                </button>

                <button
                  type="submit"
                  disabled={isPublishing}
                  className="flex items-center gap-2 px-6 py-2.5 text-xs font-bold text-white bg-emerald-700 hover:bg-emerald-800 active:bg-emerald-800 rounded-xl shadow-md shadow-emerald-600/20 transition-all cursor-pointer disabled:opacity-50"
                >
                  {isPublishing ? (
                    <>
                      <span className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                      <span>Đang tạo bài mẫu...</span>
                    </>
                  ) : (
                    <>
                      <Send size={15} />
                      <span>{composerData.scheduleType === 'now' ? 'Thêm bài mô phỏng' : 'Tạo lịch đăng mẫu'}</span>
                    </>
                  )}
                </button>
              </div>
            </div>
          </form>
        </div>
      )}
      <Dialog open={Boolean(selectedPost)} onClose={() => setSelectedPost(null)} title="Chi tiết bài viết mẫu">
        {selectedPost && <div className="dialog-body"><h3 className="task-detail-title">{selectedPost.title}</h3><p className="context-note">{selectedPost.content || 'Bài viết mẫu chỉ có tiêu đề và số liệu minh họa; chưa có nội dung đầy đủ.'}</p><dl className="confirmation-details"><div><dt>Trạng thái</dt><dd>{selectedPost.status}</dd></div><div><dt>Thời điểm mẫu</dt><dd>{selectedPost.date}</dd></div><div><dt>Kênh dự kiến</dt><dd>{selectedPost.channels || 'Facebook'}</dd></div></dl></div>}
      </Dialog>
    </div>
  );
};
