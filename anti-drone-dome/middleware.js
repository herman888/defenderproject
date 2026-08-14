export default function middleware(request) {
  const host = (request.headers.get("host") || "").split(":")[0].toLowerCase();
  const url = new URL(request.url);
  const landingHosts = new Set(["www.projectlarp.com", "projectlarp.com"]);

  if (!landingHosts.has(host)) {
    return;
  }

  if (url.pathname.startsWith("/marketing") || url.pathname.startsWith("/assets/logo")) {
    return;
  }

  url.pathname = "/marketing/index.html";
  return Response.rewrite(url);
}

export const config = {
  matcher: ["/((?!_vercel|favicon.ico).*)"],
};
