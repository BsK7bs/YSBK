export function formatRelative(iso) {
  if (!iso) return "never";
  const d = typeof iso === "string" ? new Date(iso) : iso;
  const diff = Math.floor((Date.now() - d.getTime()) / 1000);
  if (Number.isNaN(diff)) return "";
  if (diff < 5) return "just now";
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  if (diff < 86400 * 7) return `${Math.floor(diff / 86400)}d ago`;
  return d.toLocaleDateString();
}

export function formatNumber(n, digits = 0) {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return Number(n).toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

export function riskColor(risk) {
  switch (risk) {
    case "healthy":
      return "success";
    case "warning":
      return "warning";
    case "high_risk":
      return "high-risk";
    case "critical":
      return "critical";
    default:
      return "offline";
  }
}

export function riskLabel(risk) {
  switch (risk) {
    case "healthy":
      return "Healthy";
    case "warning":
      return "Warning";
    case "high_risk":
      return "High Risk";
    case "critical":
      return "Critical";
    case "offline":
      return "Offline";
    default:
      return "—";
  }
}

export function severityColor(sev) {
  switch (sev) {
    case "critical":
      return "critical";
    case "high":
      return "high-risk";
    case "medium":
    case "warning":
      return "warning";
    case "low":
      return "info";
    case "info":
    default:
      return "info";
  }
}

export function severityLabel(sev) {
  const map = { critical: "Critical", high: "High", medium: "Medium", low: "Low", info: "Info", warning: "Warning" };
  return map[sev] || (sev || "—");
}

export function alertStatusLabel(status) {
  switch (status) {
    case "open": return "Open";
    case "investigating": return "Investigating";
    case "resolved_awaiting_ack": return "Awaiting Ack";
    case "acknowledged": return "Acknowledged";
    case "closed": return "Closed";
    default: return status || "—";
  }
}

export function alertStatusColor(status) {
  switch (status) {
    case "open": return "critical";
    case "investigating": return "warning";
    case "resolved_awaiting_ack": return "warning";
    case "acknowledged": return "info";
    case "closed": return "healthy";
    default: return "offline";
  }
}

export async function copyToClipboard(text) {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch (_) {
    // Fall through to legacy method
  }
  try {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.position = "fixed";
    ta.style.top = "0";
    ta.style.left = "0";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(ta);
    return ok;
  } catch (_) {
    return false;
  }
}

export function extractError(err, fallback = "Something went wrong") {
  const d = err?.response?.data?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d)) {
    return d.map((e) => (e && (e.msg || e.message)) || JSON.stringify(e)).join(", ") || fallback;
  }
  if (d && typeof d === "object") return d.msg || d.message || fallback;
  return err?.message || fallback;
}

export const ROLE_LABELS = {
  owner: "Owner",
  admin: "Admin",
  technician: "Technician",
  viewer: "Viewer",
};

export const ROLE_ORDER = { viewer: 1, technician: 2, admin: 3, owner: 4 };

export function hasRole(user, minRole) {
  if (!user) return false;
  return (ROLE_ORDER[user.role] || 0) >= (ROLE_ORDER[minRole] || 0);
}
