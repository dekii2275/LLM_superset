type StatusCardProps = {
  name: string;
  status: "Checking" | "Connected" | "Disconnected";
  detail: string;
  href?: string;
};

export function StatusCard({ name, status, detail, href }: StatusCardProps) {
  const className = status.toLowerCase();

  return (
    <article className="status-card">
      <div className="status-card-top">
        <p className="status-name">{name}</p>
        <span className={`status-pill ${className}`}>{status}</span>
      </div>
      <p className="status-detail">
        {href ? (
          <a className="status-link" href={href} target="_blank" rel="noreferrer">
            {detail}
          </a>
        ) : (
          detail
        )}
      </p>
    </article>
  );
}
