import React, { useEffect, useState } from 'react';
import {
  ShieldCheck,
  AlertTriangle,
  Cpu,
  HardDrive,
  Trash2,
  CheckCircle2,
  XCircle,
  Download,
  Upload,
  Lock,
  Scale,
} from 'lucide-react';
import { api, apiUrl } from '../api';
import { ModelItem, ProjectSummary } from '../types';

/* ==================== AI MODEL MANAGER ==================== */
export const ModelManagerView: React.FC<{
  onNotify: (msg: string) => void;
}> = ({ onNotify }) => {
  const [models, setModels] = useState<ModelItem[]>([]);
  const [modelsDir, setModelsDir] = useState('');
  const [confirmModal, setConfirmModal] = useState<ModelItem | null>(null);
  const [localFiles, setLocalFiles] = useState<FileList | null>(null);
  const [err, setErr] = useState('');

  const loadModels = async () => {
    const res = await api.get('/api/models');
    setModels(res.models || []);
    setModelsDir(res.models_dir || '');
  };

  useEffect(() => {
    loadModels();
  }, []);

  const handleVerify = async (id: string) => {
    setErr('');
    const res = await api.post(`/api/models/${id}/verify`);
    await loadModels();
    onNotify(res.details || 'Model verification completed.');
  };

  const handleToggleActive = async (m: ModelItem) => {
    setErr('');
    try {
      await api.post(`/api/models/${m.id}/active`, { active: !m.active });
      await loadModels();
    } catch (e: any) {
      setErr(e.message);
    }
  };

  const handleRemove = async (id: string) => {
    setErr('');
    try {
      await api.del(`/api/models/${id}`);
      await loadModels();
      onNotify('Model files removed from local storage.');
    } catch (e: any) {
      setErr(e.message);
    }
  };

  const handleConfirmedInstall = async () => {
    if (!confirmModal) return;
    setErr('');
    try {
      if (localFiles && localFiles.length > 0) {
        const form = new FormData();
        form.append('user_confirmed', 'true');
        Array.from(localFiles).forEach((f) => form.append('files', f));
        await api.uploadForm(`/api/models/${confirmModal.id}/import-local`, form);
        onNotify(`Imported and verified local weights for ${confirmModal.name}.`);
      } else {
        await api.post(`/api/models/${confirmModal.id}/install`, { user_confirmed: true });
        onNotify(`Installed ${confirmModal.name}.`);
      }
      setConfirmModal(null);
      setLocalFiles(null);
      await loadModels();
    } catch (e: any) {
      setErr(e.message);
    }
  };

  const handleUpdateDir = async () => {
    await api.post('/api/models/configure-path', { models_dir: modelsDir });
    await loadModels();
    onNotify('Updated local AI models directory.');
  };

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-bold text-white">Local AI Model Manager</h2>
        <p className="text-xs text-slate-400">
          Inspect model licenses, download sizes, storage &amp; VRAM requirements, SHA256 integrity, and hardware compatibility. No model is ever downloaded without explicit confirmation.
        </p>
      </div>

      {/* Model Path Bar */}
      <div className="flex flex-wrap items-center gap-2 rounded-xl border border-slate-800 bg-[#111520] p-4 text-xs">
        <span className="font-medium text-slate-300">Local Models Directory:</span>
        <input
          value={modelsDir}
          onChange={(e) => setModelsDir(e.target.value)}
          className="flex-1 min-w-[240px] rounded border border-slate-700 bg-slate-900 px-3 py-1.5 text-white font-mono"
        />
        <button
          onClick={handleUpdateDir}
          className="rounded bg-slate-800 px-3 py-1.5 font-medium text-amber-300 hover:bg-slate-700"
        >
          Update Path
        </button>
      </div>

      {err && (
        <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-xs text-red-200">{err}</div>
      )}

      {/* Explicit Consent Confirmation Modal */}
      {confirmModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-4">
          <div className="w-full max-w-lg rounded-xl border border-amber-500/40 bg-[#131826] p-5 space-y-4 text-xs">
            <h3 className="text-base font-bold text-white">Confirm Model Installation / Local Weight Import</h3>
            <div className="space-y-1 text-slate-300">
              <div>Model: <strong>{confirmModal.name}</strong> ({confirmModal.version})</div>
              <div>Estimated Download Size: <strong className="text-amber-300">{confirmModal.download_size_mb} MB</strong></div>
              <div>Required Disk Storage: <strong>{confirmModal.required_storage_mb} MB</strong></div>
              <div>License: <strong>{confirmModal.license}</strong></div>
            </div>

            <div className="rounded border border-slate-700 bg-slate-900 p-3 space-y-2">
              <div className="font-medium text-slate-200">
                Optional Offline Import (Select `.onnx`, `.json`, or `.gguf` weight files from your computer):
              </div>
              <input
                type="file"
                multiple
                onChange={(e) => setLocalFiles(e.target.files)}
                className="w-full text-slate-300"
              />
            </div>

            <div className="flex justify-end gap-2">
              <button
                onClick={() => {
                  setConfirmModal(null);
                  setLocalFiles(null);
                }}
                className="rounded-lg border border-slate-700 px-4 py-2 text-slate-300"
              >
                Cancel
              </button>
              <button
                onClick={handleConfirmedInstall}
                className="rounded-lg bg-amber-500 px-4 py-2 font-bold text-slate-950 hover:bg-amber-400"
              >
                I Consent — Proceed ({confirmModal.download_size_mb} MB)
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        {models.map((m) => (
          <div key={m.id} className="rounded-xl border border-slate-800 bg-[#121723] p-4 flex flex-col gap-3 text-xs">
            <div className="flex items-start justify-between gap-2">
              <div>
                <h3 className="text-sm font-bold text-white">{m.name}</h3>
                <div className="text-slate-400">{m.purpose}</div>
              </div>
              <span
                className={`shrink-0 rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${
                  m.compatibility_status === 'compatible'
                    ? 'bg-emerald-500/15 text-emerald-300'
                    : m.compatibility_status === 'warning'
                    ? 'bg-amber-500/15 text-amber-300'
                    : 'bg-red-500/15 text-red-300'
                }`}
              >
                {m.compatibility_status}
              </span>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 rounded-lg bg-[#0c101a] p-2.5 text-[11px] text-slate-300">
              <div>Version: <strong>{m.version}</strong></div>
              <div>Download: <strong>{m.download_size_mb} MB</strong></div>
              <div>Storage: <strong>{m.required_storage_mb} MB</strong></div>
              <div>Min RAM: <strong>{m.min_ram_gb} GB</strong></div>
              <div>GPU Req: <strong>{m.requires_gpu ? `${m.min_vram_mb} MB VRAM` : 'CPU Ready'}</strong></div>
              <div>Offline Run: <strong>{m.internet_required_to_run ? 'No' : 'Yes (100% Offline)'}</strong></div>
            </div>

            <div className="flex flex-wrap gap-1.5 text-[11px]">
              <span className="rounded bg-slate-800 px-2 py-0.5 text-amber-300">License: {m.license}</span>
              <span
                className={`rounded px-2 py-0.5 ${
                  m.commercial_use ? 'bg-emerald-500/10 text-emerald-300' : 'bg-red-500/15 text-red-300'
                }`}
              >
                {m.commercial_use ? 'Commercial Permitted' : 'Non-Commercial Restriction'}
              </span>
              <span className="rounded bg-slate-800 px-2 py-0.5 text-slate-300">
                Languages: {m.supported_languages.join(', ')}
              </span>
            </div>

            {m.compatibility_notes.length > 0 && (
              <div className="rounded border border-amber-500/30 bg-amber-500/10 p-2 text-[11px] text-amber-200">
                {m.compatibility_notes.join(' ')}
              </div>
            )}

            <div className="text-[11px] text-slate-400">
              <div>Directory: <span className="font-mono text-slate-300">{m.model_directory}</span></div>
              {m.verified_sha256 && (
                <div className="truncate">Verified SHA256: <span className="font-mono text-emerald-400">{m.verified_sha256}</span></div>
              )}
              <div className="mt-0.5">{m.notes}</div>
            </div>

            <div className="mt-auto flex flex-wrap gap-2 pt-1">
              <span
                className={`inline-flex items-center gap-1 rounded px-2.5 py-1 font-semibold ${
                  m.installed ? 'bg-emerald-500/15 text-emerald-300' : 'bg-slate-800 text-slate-400'
                }`}
              >
                {m.installed ? <CheckCircle2 className="h-3.5 w-3.5" /> : <XCircle className="h-3.5 w-3.5" />}
                {m.installed ? 'Installed' : 'Not Installed'}
              </span>

              <button
                onClick={() => handleVerify(m.id)}
                className="rounded border border-slate-700 bg-slate-800 px-3 py-1 text-slate-200 hover:bg-slate-700"
              >
                Verify Files
              </button>

              {m.installed && (
                <button
                  onClick={() => handleToggleActive(m)}
                  className="rounded border border-amber-500/30 bg-amber-500/15 px-3 py-1 text-amber-300"
                >
                  {m.active ? 'Active' : 'Set Active'}
                </button>
              )}

              {!m.builtin && !m.installed && (
                <button
                  disabled={m.compatibility_status === 'incompatible'}
                  onClick={() => setConfirmModal(m)}
                  className="inline-flex items-center gap-1 rounded bg-amber-500 px-3 py-1 font-bold text-slate-950 hover:bg-amber-400 disabled:opacity-40"
                >
                  <Download className="h-3.5 w-3.5" /> Install / Import
                </button>
              )}

              {!m.builtin && m.installed && (
                <button
                  onClick={() => handleRemove(m.id)}
                  className="inline-flex items-center gap-1 rounded bg-red-500/20 px-3 py-1 text-red-300"
                >
                  <Trash2 className="h-3.5 w-3.5" /> Remove
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

/* ==================== HARDWARE MONITOR ==================== */
export const HardwareMonitorView: React.FC<{
  hardware: any;
  onModeChange: (mode: string) => Promise<void>;
}> = ({ hardware, onModeChange }) => {
  if (!hardware) {
    return <div className="text-sm text-slate-400">Inspecting hardware...</div>;
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-white">Hardware Monitor &amp; Rendering Profiles</h2>
        <p className="text-xs text-slate-400">
          Real-time inspection of OS, CPU, RAM, GPU/VRAM, Disk, and local rendering dependencies.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4 text-xs">
        <div className="rounded-xl border border-slate-800 bg-[#121723] p-4 space-y-1">
          <div className="text-slate-400 font-semibold">OPERATING SYSTEM</div>
          <div className="text-base font-bold text-white">{hardware.os.system} ({hardware.os.arch})</div>
          <div className="text-slate-400">Kernel {hardware.os.release}</div>
          <div className="text-amber-300">Python {hardware.os.python_version}</div>
        </div>

        <div className="rounded-xl border border-slate-800 bg-[#121723] p-4 space-y-1">
          <div className="text-slate-400 font-semibold">CPU PROCESSOR</div>
          <div className="text-sm font-bold text-white truncate">{hardware.cpu.model}</div>
          <div className="text-slate-300">
            {hardware.cpu.physical_cores} Physical / {hardware.cpu.logical_cores} Logical Cores
          </div>
          <div className="text-emerald-300">Load: {hardware.cpu.usage_percent}%</div>
        </div>

        <div className="rounded-xl border border-slate-800 bg-[#121723] p-4 space-y-1">
          <div className="text-slate-400 font-semibold">SYSTEM MEMORY &amp; GPU</div>
          <div className="text-base font-bold text-white">
            {hardware.memory.available_gb} GB Free / {hardware.memory.total_gb} GB RAM
          </div>
          <div className="text-slate-300">
            GPU: {hardware.gpu.detected ? `${hardware.gpu.total_vram_mb} MB VRAM` : 'None (0 MB VRAM — CPU Mode)'}
          </div>
        </div>

        <div className="rounded-xl border border-slate-800 bg-[#121723] p-4 space-y-1">
          <div className="text-slate-400 font-semibold">DISK SPACE</div>
          <div className="text-base font-bold text-white">{hardware.storage.free_gb} GB Free</div>
          <div className="text-slate-300">Total Volume: {hardware.storage.total_gb} GB ({hardware.storage.used_percent}% used)</div>
        </div>
      </div>

      {/* Mode Switcher */}
      <div className="rounded-xl border border-slate-800 bg-[#111520] p-5 space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-white">Select Studio Performance Profile</h3>
          <span className="text-xs text-amber-300">
            Recommended for this PC: <strong>{hardware.recommended_mode.replace('_', ' ')}</strong>
          </span>
        </div>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
          {Object.values(hardware.profiles || {}).map((prof: any) => {
            const active = hardware.active_mode === prof.id;
            return (
              <div
                key={prof.id}
                onClick={() => onModeChange(prof.id)}
                className={`cursor-pointer rounded-xl border p-4 text-xs transition ${
                  active ? 'border-amber-500 bg-[#192033]' : 'border-slate-800 bg-[#141926] hover:border-slate-700'
                }`}
              >
                <div className="flex items-center justify-between font-bold text-white text-sm">
                  <span>{prof.label}</span>
                  {active && <span className="text-[11px] text-amber-400">ACTIVE</span>}
                </div>
                <p className="mt-1.5 text-slate-400">{prof.description}</p>
                <div className="mt-2 text-[11px] text-slate-300">
                  Cycles: {prof.cycles_samples} spp • Raytrace Scale: {prof.internal_scale_pct}%
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Dependencies Table */}
      <div className="rounded-xl border border-slate-800 bg-[#111520] p-5 space-y-3">
        <h3 className="text-sm font-semibold text-white">Verified Local Runtime Dependencies</h3>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 text-xs">
          {Object.entries(hardware.dependencies || {}).map(([key, val]: [string, any]) => (
            <div key={key} className="rounded-lg border border-slate-800 bg-[#151b29] p-3 flex items-center justify-between">
              <div>
                <div className="font-semibold text-white">{key}</div>
                <div className="text-[11px] text-slate-400">{val.version || 'N/A'}</div>
              </div>
              <span
                className={`rounded px-2 py-0.5 text-[11px] font-semibold ${
                  val.installed ? 'bg-emerald-500/15 text-emerald-300' : 'bg-red-500/15 text-red-300'
                }`}
              >
                {val.installed ? 'Ready' : 'Missing'}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};

/* ==================== PROJECT & PRIVACY SETTINGS + LICENSE REPORT ==================== */
export const ProjectSettingsView: React.FC<{
  project: ProjectSummary | null;
  storage: any;
  onRefreshAll: () => Promise<void>;
  onProjectDeleted: () => Promise<void>;
  onNotify: (msg: string) => void;
}> = ({ project, storage, onRefreshAll, onProjectDeleted, onNotify }) => {
  const [settings, setSettings] = useState<any>(null);
  const [licenseReport, setLicenseReport] = useState<any>(null);
  const [uploadFile, setUploadFile] = useState<File | null>(null);
  const [uploadLicense, setUploadLicense] = useState('CC0-1.0');
  const [deleteToken, setDeleteToken] = useState('');
  const [err, setErr] = useState('');

  const loadData = async () => {
    const s = await api.get('/api/system/settings');
    setSettings(s);
    if (project) {
      const rep = await api.get(`/api/projects/${project.id}/license-report`);
      setLicenseReport(rep);
    } else {
      setLicenseReport(null);
    }
  };

  useEffect(() => {
    loadData();
  }, [project?.id]);

  const saveSettings = async () => {
    setErr('');
    try {
      const updated = await api.patch('/api/system/settings', {
        workspace_dir: settings.workspace_dir,
        models_dir: settings.models_dir,
        local_only_default: settings.local_only_default,
        allow_model_downloads: settings.allow_model_downloads,
        local_llm_url: settings.local_llm_url,
        local_llm_model: settings.local_llm_model,
      });
      setSettings(updated);
      await onRefreshAll();
      onNotify('Saved local workspace & privacy settings.');
    } catch (e: any) {
      setErr(e.message);
    }
  };

  const handleUploadAsset = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!project || !uploadFile) return;
    setErr('');
    try {
      const form = new FormData();
      form.append('file', uploadFile);
      form.append('category', 'image');
      form.append('license_spdx', uploadLicense);
      await api.uploadForm(`/api/projects/${project.id}/upload-asset`, form);
      setUploadFile(null);
      await loadData();
      onNotify('Asset uploaded locally & logged in Project Provenance Report.');
    } catch (e: any) {
      setErr(e.message);
    }
  };

  const handleCleanupTemp = async () => {
    const res = await api.post('/api/system/cleanup-temp');
    await onRefreshAll();
    onNotify(`Cleaned temporary render cache (freed ${res.freed_mb} MB).`);
  };

  const handleDeleteProject = async () => {
    if (!project) return;
    setErr('');
    try {
      await api.del(`/api/projects/${project.id}?confirm_token=${encodeURIComponent(deleteToken)}`);
      setDeleteToken('');
      await onProjectDeleted();
      onNotify('Project and all local media deleted.');
    } catch (e: any) {
      setErr(e.message);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-white">Studio Privacy, Storage, Copyright &amp; Project Settings</h2>
        <p className="text-xs text-slate-400">
          Local-only operation by default. Inspect provenance &amp; license compliance, manage local folders, or delete project data safely.
        </p>
      </div>

      {err && <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-xs text-red-200">{err}</div>}

      {settings && (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          {/* Privacy & Paths */}
          <div className="space-y-4 rounded-xl border border-slate-800 bg-[#111520] p-5 text-xs">
            <h3 className="flex items-center gap-2 text-sm font-semibold text-white">
              <Lock className="h-4 w-4 text-emerald-400" /> Local Workspace &amp; Privacy Controls
            </h3>
            <div>
              <label className="block text-slate-400 mb-1">Local Workspace Directory</label>
              <input
                value={settings.workspace_dir}
                onChange={(e) => setSettings({ ...settings, workspace_dir: e.target.value })}
                className="w-full rounded border border-slate-700 bg-slate-900 px-3 py-1.5 font-mono text-white"
              />
            </div>
            <div>
              <label className="block text-slate-400 mb-1">
                Optional Local Loopback LLM Endpoint (127.0.0.1 / localhost ONLY)
              </label>
              <input
                value={settings.local_llm_url}
                onChange={(e) => setSettings({ ...settings, local_llm_url: e.target.value })}
                placeholder="http://127.0.0.1:11434/api/chat (optional)"
                className="w-full rounded border border-slate-700 bg-slate-900 px-3 py-1.5 font-mono text-white"
              />
            </div>
            <label className="flex items-center gap-2 text-slate-300">
              <input
                type="checkbox"
                checked={Boolean(settings.local_only_default)}
                onChange={(e) => setSettings({ ...settings, local_only_default: e.target.checked })}
              />
              Enforce strict local-only video generation (zero external uploads)
            </label>
            <label className="flex items-center gap-2 text-slate-300">
              <input
                type="checkbox"
                checked={Boolean(settings.allow_model_downloads)}
                onChange={(e) => setSettings({ ...settings, allow_model_downloads: e.target.checked })}
              />
              Permit user-confirmed AI model downloads from external repositories
            </label>
            <div className="flex gap-2 pt-1">
              <button
                onClick={saveSettings}
                className="rounded-lg bg-amber-500 px-4 py-2 font-bold text-slate-950 hover:bg-amber-400"
              >
                Save Studio Settings
              </button>
              <button
                onClick={handleCleanupTemp}
                className="rounded-lg border border-slate-700 bg-slate-800 px-4 py-2 text-slate-200 hover:bg-slate-700"
              >
                Clean Temp Render Cache ({storage?.breakdown_mb?.temp || 0} MB)
              </button>
            </div>
          </div>

          {/* Asset Upload & Destructive Deletion */}
          <div className="space-y-4 rounded-xl border border-slate-800 bg-[#111520] p-5 text-xs">
            <h3 className="flex items-center gap-2 text-sm font-semibold text-white">
              <Upload className="h-4 w-4 text-amber-400" /> Verified Reference Asset Upload &amp; Data Controls
            </h3>
            {project ? (
              <>
                <form onSubmit={handleUploadAsset} className="space-y-2 border-b border-slate-800 pb-4">
                  <div className="text-slate-400">
                    Upload reference image (`.png`, `.jpg`, `.webp`) to <strong>{project.title}</strong> with provenance tracking:
                  </div>
                  <input
                    type="file"
                    accept=".png,.jpg,.jpeg,.webp"
                    onChange={(e) => setUploadFile(e.target.files?.[0] || null)}
                    className="w-full text-slate-300"
                  />
                  <div className="flex gap-2">
                    <select
                      value={uploadLicense}
                      onChange={(e) => setUploadLicense(e.target.value)}
                      className="rounded border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-white"
                    >
                      <option value="Original-User-Work">Original User-Created Work</option>
                      <option value="CC0-1.0">Public Domain / CC0-1.0</option>
                      <option value="CC-BY-4.0">CC-BY-4.0 (Attribution Required)</option>
                      <option value="Unverified-User-Upload">Unverified / Unknown Rights (Flags Warning)</option>
                    </select>
                    <button
                      type="submit"
                      disabled={!uploadFile}
                      className="rounded bg-slate-800 px-3 py-1.5 font-semibold text-amber-300 hover:bg-slate-700 disabled:opacity-40"
                    >
                      Upload &amp; Track Provenance
                    </button>
                  </div>
                </form>

                <div className="space-y-2 pt-1">
                  <div className="font-semibold text-red-400">Permanent Project Deletion</div>
                  <div className="text-slate-400">
                    Type <code className="text-red-300">DELETE</code> below to permanently erase <strong>{project.title}</strong> and its rendered files:
                  </div>
                  <div className="flex gap-2">
                    <input
                      value={deleteToken}
                      onChange={(e) => setDeleteToken(e.target.value)}
                      placeholder="Type DELETE to confirm"
                      className="rounded border border-red-500/40 bg-slate-900 px-3 py-1.5 text-white"
                    />
                    <button
                      onClick={handleDeleteProject}
                      disabled={deleteToken !== 'DELETE'}
                      className="inline-flex items-center gap-1 rounded bg-red-600 px-3 py-1.5 font-bold text-white disabled:opacity-40"
                    >
                      <Trash2 className="h-3.5 w-3.5" /> Delete Project
                    </button>
                  </div>
                </div>
              </>
            ) : (
              <div className="text-slate-400">Select an active project to upload reference assets or delete project files.</div>
            )}
          </div>
        </div>
      )}

      {/* License & Copyright Compliance Report */}
      {licenseReport && (
        <div className="rounded-xl border border-slate-800 bg-[#111520] p-5 space-y-4 text-xs">
          <div className="flex items-center justify-between">
            <h3 className="flex items-center gap-2 text-sm font-semibold text-white">
              <Scale className="h-4 w-4 text-amber-400" /> Project Copyright &amp; License Compliance Report — {licenseReport.project_title}
            </h3>
            {project && (
              <a
                href={apiUrl(`/api/projects/${project.id}/manifest`)}
                target="_blank"
                rel="noreferrer"
                className="text-amber-300 hover:underline"
              >
                Export Project Manifest JSON
              </a>
            )}
          </div>

          {(licenseReport.compliance_flags || []).length > 0 && (
            <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-3 text-amber-200 space-y-1">
              {licenseReport.compliance_flags.map((f: string, idx: number) => (
                <div key={idx}>• {f}</div>
              ))}
            </div>
          )}

          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            {(licenseReport.core_software_stack || []).map((item: any, idx: number) => (
              <div key={idx} className="rounded-lg border border-slate-800 bg-[#151b29] p-3 space-y-1">
                <div className="font-semibold text-white">
                  {item.component} <span className="text-amber-300">({item.version})</span>
                </div>
                <div className="text-emerald-300">SPDX License: {item.license}</div>
                <div className="text-slate-400">{item.redistribution_notes}</div>
              </div>
            ))}
          </div>

          <div className="rounded-lg border border-slate-800 bg-[#0b0e16] p-3 text-slate-400">
            {licenseReport.legal_disclaimer}
          </div>
        </div>
      )}
    </div>
  );
};
