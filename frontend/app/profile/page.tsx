import Link from "next/link";
import { AppLayout } from "@/components/layout/AppLayout";
import { Icon } from "@/components/ui/Icon";

export default function ProfilePage() {
  return (
    <AppLayout singleColumn>
      <section className="route-page">
        <header className="route-heading">
          <p className="panel-eyebrow">KHÔNG GIAN LÀM VIỆC</p>
          <h1>Hồ sơ</h1>
          <p>Thông tin không gian làm việc và nguồn dữ liệu phân tích đã kết nối.</p>
        </header>
        <section className="profile-card" aria-label="Hồ sơ Nhóm Phân tích">
          <div className="profile-card-heading">
            <span className="profile-avatar profile-avatar-large">AN</span>
            <div>
              <h2>Nhóm Phân tích</h2>
              <p>Không gian làm việc phân tích</p>
            </div>
          </div>
          <div className="profile-detail">
            <span className="source-icon"><Icon name="database" size={17} /></span>
            <div><small>NGUỒN DỮ LIỆU ĐÃ KẾT NỐI</small><strong>Taxi Vàng NYC</strong></div>
            <span className="source-status profile-connected"><span className="status-dot connected" />Đã kết nối</span>
          </div>
          <Link className="profile-dashboard-link" href="/dashboard">Mở bảng điều khiển NYC Taxi <Icon name="arrow-up-right" size={15} /></Link>
        </section>
      </section>
    </AppLayout>
  );
}
