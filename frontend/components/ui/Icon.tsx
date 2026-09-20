import type { SVGProps } from "react";

export type IconName =
  | "sparkle"
  | "plus"
  | "message"
  | "database"
  | "chart"
  | "menu"
  | "arrow-up-right"
  | "arrow-up"
  | "code"
  | "copy"
  | "check"
  | "close"
  | "clock";

type IconProps = SVGProps<SVGSVGElement> & {
  name: IconName;
  size?: number;
};

export function Icon({ name, size = 18, ...props }: IconProps) {
  const shared = {
    fill: "none",
    stroke: "currentColor",
    strokeLinecap: "round" as const,
    strokeLinejoin: "round" as const,
    strokeWidth: 1.7,
  };

  let content;
  switch (name) {
    case "sparkle":
      content = <><path d="m12 2 1.9 6.1L20 10l-6.1 1.9L12 18l-1.9-6.1L4 10l6.1-1.9L12 2Z" /><path d="m19 15 .8 2.2L22 18l-2.2.8L19 21l-.8-2.2L16 18l2.2-.8L19 15Z" /></>;
      break;
    case "plus":
      content = <path d="M12 5v14M5 12h14" />;
      break;
    case "message":
      content = <><path d="M20 11.5a7.5 7.5 0 0 1-7.5 7.5H5l1.5-3A7.5 7.5 0 1 1 20 11.5Z" /><path d="M8.5 11.5h7M8.5 8.5h4.5" /></>;
      break;
    case "database":
      content = <><ellipse cx="12" cy="5" rx="8" ry="3" /><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3" /></>;
      break;
    case "chart":
      content = <><path d="M4 19V5M4 19h16" /><path d="m7 15 3-4 3 2 5-6" /><path d="M17 7h1v1" /></>;
      break;
    case "menu":
      content = <><path d="M4 6h16M4 12h16M4 18h16" /></>;
      break;
    case "arrow-up-right":
      content = <><path d="M7 17 17 7M8 7h9v9" /></>;
      break;
    case "arrow-up":
      content = <><path d="M12 19V5M6 11l6-6 6 6" /></>;
      break;
    case "code":
      content = <><path d="m8 8-4 4 4 4M16 8l4 4-4 4M14 5l-4 14" /></>;
      break;
    case "copy":
      content = <><rect x="8" y="8" width="12" height="12" rx="2" /><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3" /></>;
      break;
    case "check":
      content = <path d="m5 12 4 4L19 6" />;
      break;
    case "close":
      content = <><path d="m6 6 12 12M18 6 6 18" /></>;
      break;
    case "clock":
      content = <><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></>;
      break;
  }

  return (
    <svg
      aria-hidden="true"
      width={size}
      height={size}
      viewBox="0 0 24 24"
      {...shared}
      {...props}
    >
      {content}
    </svg>
  );
}
