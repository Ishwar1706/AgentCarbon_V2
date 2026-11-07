import React, { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, downloadFile } from "../api/client.js";
import { useAuth } from "../state/AuthContext.jsx";
import { Badge, Card, Empty, ErrorBox, Field, Table, fmt, useAsync, when } from "../components/UI.jsx";

const TYPES = ["CALIBRATION_CERTIFICATE", "MAINTENANCE_RECORD", "UTILITY_BILL", "METER_PHOTO", "REPAIR_REPORT", "OTHER"];

export default function Evidence() {
  const { user, companyId } = useAuth();
  const [qs, setQs] = useSearchParams();
  const p = { company_id: companyId };
  const claims = useAsync(() => api.get("/dashboard/claims", p), [companyId]);
  const claimId = qs.get("claim") || claims.data?.[0]?.claim_id || "";
  const docs = useAsync(() => (claimId ? api.get("/documents", { ...p, claim_id: claimId }) : Promise.resolve([])), [companyId, claimId]);
  const packet = useAsync(() => (claimId ? api.get("/verifications/runs", { ...p, claim_id: claimId }) : Promise.resolve([])), [companyId, claimId]);
  const [type, setType] = useState("MAINTENANCE_RECORD");
  const [label, setLabel] = useState("USER_UPLOADED");
  const [file, setFile] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  if (!companyId) return <Empty text="No company selected." />;

  const upload = async () => {
    setBusy(true); setError("");
    try {
      const form = new FormData();
      form.append("claim_id", claimId); form.append("document_type", type); form.append("data_label", label); form.append("file", file);
      await api.upload("/documents/upload", form, p);
      setFile(null); docs.reload();
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  };
  const verify = async (id, status) => {
    const note = status === "REJECTED" ? window.prompt("Reason for rejection?") || "" : "";
    try { await api.patch(`/documents/${id}/verify`, { status, note }, p); docs.reload(); } catch (e) { setError(e.message); }
  };
  const canUpload = ["PLANT_OPERATOR", "ADMIN"].includes(user.role);
  return (
    <>
      <div className="page-title"><h1>Supporting evidence</h1>
        <p>Calibration certificates, maintenance records and other documents attached to a claim. Verified documents count towards the evidence agent's assessment.</p></div>
      <Card>
        <Field label="Claim"><select value={claimId} onChange={(e) => setQs({ claim: e.target.value })}>{(claims.data || []).map((c) => <option key={c.claim_id} value={c.claim_id}>{c.month_label.replace("_", " ")} — {c.claim_id.replace(/^sim-/, "")}</option>)}</select></Field>
      </Card>
      {canUpload && (
        <Card title="Upload evidence" subtitle="PDF, PNG, JPG, TXT, CSV or JSON up to 10 MB. File contents are checked against the declared type.">
          <div className="row">
            <Field label="Type"><select value={type} onChange={(e) => setType(e.target.value)}>{TYPES.map((t) => <option key={t}>{t}</option>)}</select></Field>
            <Field label="Data label"><select value={label} onChange={(e) => setLabel(e.target.value)}><option>USER_UPLOADED</option><option>SYNTHETIC_DEMO</option></select></Field>
            <Field label="File"><input type="file" onChange={(e) => setFile(e.target.files[0])} /></Field>
            <button className="btn primary" disabled={!file || busy} onClick={upload}>Upload</button>
          </div>
        </Card>
      )}
      <ErrorBox message={error || docs.error} />
      <Card title="Documents for this claim">
        <Table rows={(docs.data || []).map((d) => ({ ...d, id: d.document_id }))} empty="No documents uploaded for this claim." columns={[
          { key: "document_type", label: "Type", render: (d) => d.document_type.replaceAll("_", " ") }, { key: "original_filename", label: "File" },
          { key: "size_bytes", label: "Size KB", num: true, render: (d) => fmt(d.size_bytes / 1024, 1) }, { key: "data_label", label: "Label", render: (d) => <Badge value={d.data_label} /> },
          { key: "verification_status", label: "Status", render: (d) => <Badge value={d.verification_status} /> }, { key: "uploaded_at", label: "Uploaded", render: (d) => when(d.uploaded_at) },
          { key: "a", label: "", render: (d) => (
            <div className="row">
              <button className="btn sm" onClick={() => downloadFile(`/documents/${d.document_id}/download`, p, d.original_filename)}>Download</button>
              {user.role === "AUDITOR" && d.verification_status === "PENDING" && (<>
                <button className="btn sm" onClick={() => verify(d.document_id, "VERIFIED")}>Verify</button>
                <button className="btn sm danger" onClick={() => verify(d.document_id, "REJECTED")}>Reject</button></>)}
            </div>) },
        ]} />
      </Card>
    </>
  );
}
