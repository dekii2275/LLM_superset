import Link from "next/link";
import { AppLayout } from "@/components/layout/AppLayout";
import { Icon } from "@/components/ui/Icon";

export default function ProfilePage() {
  return (
    <AppLayout singleColumn>
      <section className="route-page">
        <header className="route-heading">
          <p className="panel-eyebrow">WORKSPACE</p>
          <h1>Profile</h1>
          <p>Workspace identity and connected analytics source.</p>
        </header>
        <section className="profile-card" aria-label="Analytics Team profile">
          <div className="profile-card-heading">
            <span className="profile-avatar profile-avatar-large">AN</span>
            <div>
              <h2>Analytics Team</h2>
              <p>Analytics workspace</p>
            </div>
          </div>
          <div className="profile-detail">
            <span className="source-icon"><Icon name="database" size={17} /></span>
            <div><small>CONNECTED DATA SOURCE</small><strong>NYC Yellow Taxi</strong></div>
            <span className="source-status profile-connected"><span className="status-dot connected" />Connected</span>
          </div>
          <Link className="profile-dashboard-link" href="/dashboard">Open NYC Taxi dashboard <Icon name="arrow-up-right" size={15} /></Link>
        </section>
      </section>
    </AppLayout>
  );
}
