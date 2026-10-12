function formatDetailItem(item) {
  if (item == null) return "";
  if (typeof item === "string") return item;
  if (typeof item !== "object") return String(item);
  const msg = typeof item.msg === "string" ? item.msg : "";
  const loc = Array.isArray(item.loc)
    ? item.loc.filter((part) => part !== "body" && part !== "query" && part !== "path").join(".")
    : "";
  if (msg && loc) return loc + "：" + msg;
  if (msg) return msg;
  if (loc) return loc;
  if (typeof item.detail === "string") return item.detail;
  return "";
}

function formatApiDetail(detail) {
  if (detail == null || detail === "") return "";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map(formatDetailItem).filter(Boolean).join("；");
  }
  if (typeof detail === "object") {
    if (typeof detail.msg === "string" && detail.msg) return detail.msg;
    if (typeof detail.detail === "string") return detail.detail;
    if (Array.isArray(detail.detail) || (detail.detail && typeof detail.detail === "object")) {
      return formatApiDetail(detail.detail);
    }
    return formatDetailItem(detail);
  }
  return String(detail);
}

function formatApiError(err) {
  if (!err) return "請求失敗";
  if (typeof err === "string") return formatApiDetail(err) || err;
  if (err.detail) return formatApiDetail(err.detail) || "請求失敗";
  const message = formatApiDetail(err.message);
  return message || err.message || "請求失敗";
}

async function api(url, options = {}) {
  const res = await fetch(url, { credentials: "include", ...options });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(formatApiDetail(data.detail) || "請求失敗");
  }
  return data;
}

function formBody(obj) {
  const body = new FormData();
  Object.entries(obj).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") body.append(key, value);
  });
  return body;
}
