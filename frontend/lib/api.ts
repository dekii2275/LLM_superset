export function apiUrl(path: string): string {
  const baseUrl = process.env.NEXT_PUBLIC_API_URL?.replace(/\/+$/, "");
  return baseUrl ? `${baseUrl}${path}` : "";
}

export async function checkEndpoint(url: string): Promise<boolean> {
  if (!url) return false;

  try {
    const response = await fetch(url, { cache: "no-store" });
    return response.ok;
  } catch {
    return false;
  }
}
