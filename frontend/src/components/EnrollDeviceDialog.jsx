import React, { useCallback, useEffect, useState } from "react";
import {
  Download,
  ShieldCheck,
  Loader2,
  Check,
  Info,
  AlertTriangle,
  RefreshCw,
  Copy,
} from "lucide-react";
import { toast } from "sonner";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "./ui/dialog";
import { Input } from "./ui/input";
import { Label } from "./ui/label";
import { Button } from "./ui/button";
import { api, API_BASE } from "../lib/api";
import { useAuth } from "../contexts/AuthContext";
import { copyToClipboard, extractError, formatRelative } from "../lib/format";

/**
 * Download Agent dialog — the ONE customer install flow.
 *
 *   Dashboard -> Download Agent -> DigitalTwinAgentSetup_<code>.exe
 *
 * Steps performed by this component:
 *   1. Fetches ``/api/agent/installer/info`` to check whether the compiled
 *      Windows EXE is available (produced by the "Build Windows Agent
 *      Installer" GitHub Actions workflow).
 *   2. Clicking "Download Agent" hits ``/api/agent/installer/download`` which
 *      mints a single-use pairing code, streams the EXE back with the code
 *      encoded in the filename, and returns the raw code via a response
 *      header. The browser saves the file with that name.
 *   3. We then poll ``/api/agent/installer/verify?code=...`` every 5s until
 *      the paired device shows up in the fleet, giving the operator a live
 *      "Waiting for the device to come online..." indicator.
 */
export default function EnrollDeviceDialog({ open, onOpenChange, onEnrolled }) {
  const { accessToken } = useAuth();
  const [info, setInfo] = useState(null);
  const [infoLoading, setInfoLoading] = useState(false);
  const [label, setLabel] = useState("");
  const [downloading, setDownloading] = useState(false);
  const [downloadPct, setDownloadPct] = useState(null); // null=idle, -1=indeterminate, 0-100=percent
  const [downloadBytes, setDownloadBytes] = useState(null);
  const [downloadedCode, setDownloadedCode] = useState(null);
  const [verifying, setVerifying] = useState(false);
  const [verifyStatus, setVerifyStatus] = useState(null); // {paired, device}

  const loadInfo = useCallback(async () => {
    setInfoLoading(true);
    try {
      const { data } = await api.get("/agent/installer/info");
      setInfo(data);
    } catch (e) {
      setInfo(null);
    } finally {
      setInfoLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) {
      loadInfo();
      setDownloadedCode(null);
      setVerifyStatus(null);
      setLabel("");
    }
  }, [open, loadInfo]);

  // Poll the verify endpoint until the device appears online
  useEffect(() => {
    if (!downloadedCode) return;
    let cancelled = false;
    setVerifying(true);
    const tick = async () => {
      try {
        const { data } = await api.get("/agent/installer/verify", {
          params: { code: downloadedCode },
        });
        if (cancelled) return;
        setVerifyStatus(data);
        if (data?.paired && data?.device) {
          setVerifying(false);
          onEnrolled?.(data.device);
          return; // stop polling
        }
      } catch (e) {
        // Non-fatal — could be transient network or code expiry
      }
      if (!cancelled) setTimeout(tick, 5000);
    };
    tick();
    return () => {
      cancelled = true;
    };
  }, [downloadedCode, onEnrolled]);

  const downloadAgent = async () => {
    setDownloading(true);
    setDownloadPct(-1); // indeterminate until Content-Length known
    setDownloadBytes(0);
    try {
      // ------------------------------------------------------------------
      // Native-browser download flow (fixes "downloads halfway" bug).
      //
      // Step 1: hit /download-init to mint a short-lived signed JWT +
      //         pairing code. Uses normal bearer-token auth.
      // Step 2: hand the token to the browser via a hidden <a> click on
      //         /download?token=<jwt>. The browser's native download
      //         manager takes over from there — bytes stream straight
      //         to disk, with proper Content-Length, HTTP Range/resume,
      //         and no JS-side blob buffering. This eliminates the
      //         previous failure modes where large (~200 MB) transfers
      //         got killed by React re-render pressure or ingress
      //         idle-timeouts on chunked responses.
      // ------------------------------------------------------------------
      const initRes = await api.post("/agent/installer/download-init", null, {
        params: label ? { label } : {},
      });
      const {
        download_token: token,
        pairing_code: code,
        filename,
      } = initRes.data || {};
      if (!token) {
        toast.error("Backend did not return a download token — try again.");
        return;
      }

      const url = new URL(
        `${API_BASE}/agent/installer/download`,
        window.location.origin,
      );
      url.searchParams.set("token", token);
      if (label) url.searchParams.set("label", label);

      // Trigger the browser's native download manager. We do NOT read
      // the body in JS — that's the whole point of this flow: the
      // response streams straight into the OS-level Downloads folder,
      // no memory pressure on the tab.
      const a = document.createElement("a");
      a.href = url.toString();
      a.download = filename || `DigitalTwinAgentSetup_${code || "bundle"}.zip`;
      a.rel = "noopener";
      a.target = "_self";
      document.body.appendChild(a);
      a.click();
      a.remove();

      setDownloadedCode(code || null);
      toast.success("Download started — check your browser's download tray.");
    } catch (e) {
      const detail = extractError
        ? extractError(e)
        : e?.response?.data?.detail || e?.message;
      if (e?.response?.status === 503) {
        toast.error(detail || "Installer not built yet.");
        loadInfo();
      } else {
        toast.error(
          detail ||
            "Could not start the download. Please check your connection and try again."
        );
      }
      // eslint-disable-next-line no-console
      console.error("[installer download] failed:", e);
    } finally {
      setDownloading(false);
      setDownloadPct(null);
      setDownloadBytes(null);
    }
  };

  const restart = () => {
    setDownloadedCode(null);
    setVerifyStatus(null);
    setLabel("");
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="sm:max-w-lg glass"
        data-testid="download-agent-dialog"
      >
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Download className="h-5 w-5 text-primary" />
            Download Agent
          </DialogTitle>
          <DialogDescription>
            One installer per device. {info?.bundle
              ? "Download the ZIP, extract all files into any folder, then double-click the installer .exe inside."
              : "Download and double-click on the target Windows machine."}{" "}
            The installer registers the service, pairs with the backend, and
            appears online here automatically.
          </DialogDescription>
        </DialogHeader>

        {infoLoading && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground py-6">
            <Loader2 className="h-4 w-4 animate-spin" /> Checking installer availability…
          </div>
        )}

        {!infoLoading && info && !info.available && (
          <UnavailableCard info={info} onRetry={loadInfo} />
        )}

        {!infoLoading && info && info.available && !downloadedCode && (
          <ReadyToDownload
            info={info}
            label={label}
            setLabel={setLabel}
            downloading={downloading}
            downloadPct={downloadPct}
            downloadBytes={downloadBytes}
            onDownload={downloadAgent}
          />
        )}

        {downloadedCode && (
          <WaitingForDevice
            code={downloadedCode}
            info={info}
            verifying={verifying}
            status={verifyStatus}
            onRestart={restart}
            onClose={() => onOpenChange(false)}
          />
        )}
      </DialogContent>
    </Dialog>
  );
}

function ReadyToDownload({ info, label, setLabel, downloading, downloadPct, downloadBytes, onDownload }) {
  const totalBytes = info.bundle ? (info.bundle_size || info.size || 0) : (info.size || 0);
  const sizeMB = Math.max(1, Math.round(totalBytes / (1024 * 1024)));
  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-primary/25 bg-primary/5 p-3 text-xs text-primary flex items-start gap-2">
        <ShieldCheck className="h-4 w-4 mt-0.5 flex-shrink-0" />
        <div>
          Version <span className="font-medium">{info.version}</span> · Windows x64
          · {sizeMB} MB {info.bundle ? "(ZIP bundle)" : ""} · updated {formatRelative(info.updated_at)}.
          Each download contains a fresh single-use pairing code baked into the
          installer filename — never share the file with another machine.
        </div>
      </div>
      {info.bundle && (
        <div className="rounded-xl border border-amber-500/25 bg-amber-500/5 p-3 text-xs text-amber-500 flex items-start gap-2">
          <ShieldCheck className="h-4 w-4 mt-0.5 flex-shrink-0" />
          <div>
            <div className="font-medium mb-0.5">Important — how to install</div>
            <div className="text-amber-500/80">
              1. Right-click the downloaded <code>.zip</code>, choose
              "Extract All…", open the extracted folder.<br />
              2. Double-click <code className="font-semibold">install.cmd</code>
              {" "}(not the <code>.exe</code>) — the <code>.cmd</code> file
              launches the installer with the correct backend URL. Running
              the raw <code>.exe</code> will fail at the pairing step with
              a "Cannot reach backend" error.
            </div>
          </div>
        </div>
      )}
      <div>
        <Label htmlFor="agent-label">Device label (optional)</Label>
        <Input
          id="agent-label"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          placeholder="Lab Room A · iMac #3"
          className="mt-1.5"
          data-testid="agent-label-input"
        />
        <div className="mt-1 text-[11px] text-muted-foreground">
          The label appears in the fleet list once the device comes online.
        </div>
      </div>
      <DialogFooter>
        <div className="w-full space-y-2">
          {downloading && (
            <div className="w-full">
              <div className="flex justify-between text-[11px] text-muted-foreground mb-1">
                <span>
                  {downloadPct !== null && downloadPct >= 0
                    ? `Downloading… ${downloadPct}%`
                    : "Downloading…"}
                </span>
                <span>
                  {downloadBytes !== null
                    ? `${(downloadBytes / (1024 * 1024)).toFixed(1)} MB`
                    : ""}
                </span>
              </div>
              <div className="h-1.5 w-full rounded-full bg-muted overflow-hidden">
                {downloadPct !== null && downloadPct >= 0 ? (
                  <div
                    className="h-full bg-primary transition-all duration-200 ease-out"
                    style={{ width: `${downloadPct}%` }}
                  />
                ) : (
                  <div className="h-full w-1/3 bg-primary animate-pulse rounded-full" />
                )}
              </div>
            </div>
          )}
          <Button
            onClick={onDownload}
            disabled={downloading}
            data-testid="download-agent-btn"
            className="w-full sm:w-auto"
          >
            {downloading ? (
              <>
                <Loader2 className="h-4 w-4 animate-spin mr-2" />
                {downloadPct !== null && downloadPct >= 0
                  ? `Downloading ${downloadPct}%…`
                  : "Preparing installer…"}
              </>
            ) : (
              <>
                <Download className="h-4 w-4 mr-2" /> Download Agent
              </>
            )}
          </Button>
        </div>
      </DialogFooter>
    </div>
  );
}

function WaitingForDevice({ code, info, verifying, status, onRestart, onClose }) {
  const paired = status?.paired && status?.device;
  const isBundle = !!info?.bundle;
  const downloadedFilename = isBundle
    ? `DigitalTwinAgentSetup_${code}.zip`
    : `DigitalTwinAgentSetup_${code}.exe`;
  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-border bg-foreground/[0.02] p-4">
        <div className="text-[11px] text-muted-foreground uppercase tracking-widest">
          {isBundle ? "Bundle downloaded" : "Installer downloaded"}
        </div>
        <div className="mt-1 font-mono text-sm font-semibold tracking-widest">
          {downloadedFilename}
        </div>
        <div className="mt-3 flex items-center gap-2">
          <Button
            size="sm"
            variant="secondary"
            onClick={async () => {
              const ok = await copyToClipboard(code);
              if (ok) toast.success("Pairing code copied");
            }}
          >
            <Copy className="h-3.5 w-3.5 mr-1.5" /> Copy code
          </Button>
        </div>
      </div>

      <ol className="space-y-2 text-sm text-muted-foreground">
        <StepLine done text="Download complete" />
        {isBundle && (
          <StepLine done text="Extract all files from the .zip into a single folder" />
        )}
        <StepLine
          done
          text={
            isBundle
              ? "Double-click install.cmd inside the extracted folder"
              : "Double-click the installer on the target Windows machine"
          }
        />
        <StepLine
          done={paired}
          spinning={!paired && verifying}
          text={
            paired
              ? `Device ${status.device.hostname} is online`
              : "Waiting for the device to come online…"
          }
        />
      </ol>

      {paired ? (
        <div className="rounded-xl border border-emerald-500/40 bg-emerald-500/10 p-3 text-sm text-emerald-400 flex items-start gap-2">
          <Check className="h-4 w-4 mt-0.5 flex-shrink-0" />
          <div>
            <div className="font-medium">Successfully paired</div>
            <div className="text-xs mt-0.5">
              {status.device.hostname} · {status.device.status || "online"} ·
              first seen {formatRelative(status.device.last_seen)}
            </div>
          </div>
        </div>
      ) : (
        <div className="rounded-xl border border-amber-500/25 bg-amber-500/5 p-3 text-xs text-amber-400 flex items-start gap-2">
          <Info className="h-3.5 w-3.5 mt-0.5 flex-shrink-0" />
          <div>
            The pairing code expires 10 minutes from download. If the target
            machine cannot be reached in time, close this dialog and start a
            fresh download.
          </div>
        </div>
      )}

      <DialogFooter className="gap-2">
        <Button variant="secondary" onClick={onRestart}>
          <RefreshCw className="h-4 w-4 mr-1.5" /> New download
        </Button>
        <Button onClick={onClose} data-testid="agent-download-done-btn">
          Done
        </Button>
      </DialogFooter>
    </div>
  );
}

function UnavailableCard({ info, onRetry }) {
  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 p-4 text-sm flex items-start gap-3">
        <AlertTriangle className="h-5 w-5 text-amber-500 flex-shrink-0" />
        <div>
          <div className="font-medium text-amber-500">Installer not built yet</div>
          <div className="text-xs text-muted-foreground mt-1">
            {info.reason}
          </div>
        </div>
      </div>
      <div className="rounded-lg border border-border bg-foreground/[0.02] p-3 text-xs text-muted-foreground space-y-2">
        <div className="font-semibold text-foreground">
          To publish the installer:
        </div>
        <ol className="list-decimal list-inside space-y-1">
          <li>Push a git tag matching <code>v*.*.*</code> (e.g. <code>v2.1.0</code>), or</li>
          <li>
            Run the
            {" "}
            <span className="font-mono">Build Windows Agent Installer</span>
            {" "}
            workflow manually from the Actions tab.
          </li>
        </ol>
        <div className="pt-1">
          The workflow builds <code>DigitalTwinAgentSetup.exe</code> on a
          Windows runner and attaches it to the matching GitHub Release; this
          backend then serves it automatically.
        </div>
      </div>
      <DialogFooter>
        <Button variant="secondary" onClick={onRetry} data-testid="installer-refresh-btn">
          <RefreshCw className="h-4 w-4 mr-1.5" /> Check again
        </Button>
      </DialogFooter>
    </div>
  );
}

function StepLine({ done, spinning, text }) {
  return (
    <li className="flex items-center gap-2">
      {done ? (
        <span className="h-4 w-4 rounded-full bg-emerald-500/20 flex items-center justify-center">
          <Check className="h-2.5 w-2.5 text-emerald-400" />
        </span>
      ) : spinning ? (
        <Loader2 className="h-4 w-4 animate-spin text-primary" />
      ) : (
        <span className="h-4 w-4 rounded-full border border-border" />
      )}
      <span className={done ? "text-foreground" : ""}>{text}</span>
    </li>
  );
}
