import React, { useEffect, useState } from 'react';
import {
  Film,
  PlusCircle,
  Cpu,
  HardDrive,
  Play,
  AlertTriangle,
  Sparkles,
  CheckCircle2,
  Clock,
  FolderOpen,
  Layers,
  Download,
  FileText,
  Loader2,
  XCircle,
} from 'lucide-react';
import { api, apiUrl, basenameFromPath } from '../api';
import { JobItem, NavSection, ProjectSummary } from '../types';

interface DashboardProps {
  projects: ProjectSummary[];
  activeProject: ProjectSummary | null;
  jobs: JobItem[];
  hardware: any;
  storage: any;
  onSelectProject: (id: string, targetNav?: NavSection) => void;
  onNavigate: (nav: NavSection) => void;
  onQuickCreateSample: (sampleKey: string) => Promise<void>;
}

export const DashboardView: React.FC<DashboardProps> = ({
  projects,
  activeProject,
  jobs,
  hardware,
  storage,
  onSelectProject,
  onNavigate,
  onQuickCreateSample,
}) => {
  const [busySample, setBusySample] = useState<string | null>(null);
  const runningJobs = jobs.filter((j) => j.status === 'running' || j.status === 'queued' || j.status === 'paused');
  const exportedCount = projects.filter((p) => p.export_status === 'completed' || p.export_status === 'completed_with_warnings').length;

  const handleSample = async (key: string) => {
    setBusySample(key);
    try {
      await onQuickCreateSample(key);
    } finally {
      setBusySample(null);
    }
  };

  return (
    <div className="space-y-6">
      {/* Hero Banner */}
      <div className="rounded-xl border border-amber-500/25 bg-gradient-to-r from-[#131826] via-[#171d2e] to-[#1d1624] p-6 shadow-lg">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <div className="inline-flex items-center gap-2 rounded-full border border-amber-500/30 bg-amber-500/10 px-3 py-1 text-xs font-medium text-amber-300">
              <Sparkles className="h-3.5 w-3.5" />
              100% Local • Zero Paid APIs • Real Blender 3D + Local TTS
            </div>
            <h1 className="mt-2.5 text-2xl font-bold tracking-tight text-white">
              SIDD AI VIDEO STUDIO
            </h1>
            <p className="mt-1 max-w-2xl text-sm text-slate-300">
              Transform English, Urdu (اردو), and Roman Urdu scripts into animated 3D videos with articulated characters,
              jaw viseme lip-sync, choreographed combat, procedural music &amp; foley, and verified H.264 MP4 export.
            </p>
          </div>
          <div className="flex flex-wrap gap-3">
            <button
              onClick={() => onNavigate('create')}
              className="inline-flex items-center gap-2 rounded-lg bg-amber-500 px-4 py-2.5 text-sm font-semibold text-slate-950 shadow hover:bg-amber-400 transition"
            >
              <PlusCircle className="h-4 w-4" />
              Create New Video
            </button>
            {activeProject && (
              <button
                onClick={() => onNavigate('storyboard')}
                className="inline-flex items-center gap-2 rounded-lg border border-slate-700 bg-slate-800/80 px-4 py-2.5 text-sm font-medium text-slate-100 hover:bg-slate-700 transition"
              >
                <Layers className="h-4 w-4 text-amber-400" />
                Open Active Storyboard
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <div className="rounded-xl border border-slate-800 bg-[#121723] p-4">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>LOCAL PROJECTS</span>
            <FolderOpen className="h-4 w-4 text-amber-400" />
          </div>
          <div className="mt-2 text-2xl font-bold text-white">{projects.length}</div>
          <div className="mt-1 text-xs text-slate-400">{exportedCount} verified MP4 exports</div>
        </div>

        <div className="rounded-xl border border-slate-800 bg-[#121723] p-4">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>ACTIVE RENDER QUEUE</span>
            <Clock className="h-4 w-4 text-sky-400" />
          </div>
          <div className="mt-2 text-2xl font-bold text-white">{runningJobs.length}</div>
          <div className="mt-1 text-xs text-slate-400">
            {runningJobs[0] ? runningJobs[0].current_stage : 'Idle — ready to render'}
          </div>
        </div>

        <div className="rounded-xl border border-slate-800 bg-[#121723] p-4">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>RENDER ENGINE &amp; HARDWARE</span>
            <Cpu className="h-4 w-4 text-emerald-400" />
          </div>
          <div className="mt-2 text-lg font-bold text-white capitalize">
            {(hardware?.active_mode || 'low_resource').replace('_', ' ')}
          </div>
          <div className="mt-1 text-xs text-slate-400 truncate">
            {hardware
              ? `${hardware.cpu.logical_cores} CPU threads • ${hardware.memory.available_gb} GB free RAM • ${
                  hardware.gpu.detected ? 'GPU Ready' : 'CPU Raytracing'
                }`
              : 'Inspecting hardware...'}
          </div>
        </div>

        <div className="rounded-xl border border-slate-800 bg-[#121723] p-4">
          <div className="flex items-center justify-between text-xs text-slate-400">
            <span>LOCAL STORAGE</span>
            <HardDrive className="h-4 w-4 text-purple-400" />
          </div>
          <div className="mt-2 text-2xl font-bold text-white">
            {storage ? `${storage.studio_total_mb} MB` : '0 MB'}
          </div>
          <div className="mt-1 text-xs text-slate-400">
            {storage ? `${storage.disk_free_gb} GB free on disk` : 'Local workspace active'}
          </div>
        </div>
      </div>

      {/* Empty State OR Projects Grid */}
      {projects.length === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-700 bg-[#111520] p-8 text-center">
          <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-amber-500/15 text-amber-400">
            <Film className="h-6 w-6" />
          </div>
          <h2 className="mt-3 text-lg font-semibold text-white">No Video Projects Yet</h2>
          <p className="mx-auto mt-1 max-w-xl text-sm text-slate-400">
            Start from scratch with your own English, Urdu, or Roman Urdu story, or launch one of our built-in
            cinematic historical starter scripts to generate a storyboard and render your first 3D MP4 immediately.
          </p>
          <div className="mt-5 flex flex-wrap justify-center gap-3">
            <button
              onClick={() => onNavigate('create')}
              className="rounded-lg bg-amber-500 px-4 py-2 text-sm font-semibold text-slate-950 hover:bg-amber-400 transition"
            >
              Create Custom Project
            </button>
            <button
              disabled={busySample !== null}
              onClick={() => handleSample('en_historical_fortress')}
              className="rounded-lg border border-slate-700 bg-slate-800 px-4 py-2 text-sm font-medium text-slate-200 hover:bg-slate-700 disabled:opacity-50"
            >
              {busySample === 'en_historical_fortress' ? 'Creating...' : 'Quickstart: Crimson Fortress (English)'}
            </button>
            <button
              disabled={busySample !== null}
              onClick={() => handleSample('roman_ur_adventure')}
              className="rounded-lg border border-slate-700 bg-slate-800 px-4 py-2 text-sm font-medium text-slate-200 hover:bg-slate-700 disabled:opacity-50"
            >
              {busySample === 'roman_ur_adventure' ? 'Creating...' : 'Quickstart: Qilay Ki Hifazat (Roman Urdu)'}
            </button>
            <button
              disabled={busySample !== null}
              onClick={() => handleSample('ur_cinematic_story')}
              className="rounded-lg border border-slate-700 bg-slate-800 px-4 py-2 text-sm font-medium text-slate-200 hover:bg-slate-700 disabled:opacity-50"
            >
              {busySample === 'ur_cinematic_story' ? 'Creating...' : 'Quickstart: قدیم قلعہ (Urdu)'}
            </button>
          </div>
        </div>
      ) : (
        <div className="rounded-xl border border-slate-800 bg-[#111520] p-5">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-base font-semibold text-white">Your Local Studio Projects</h2>
            <button
              onClick={() => onNavigate('create')}
              className="text-xs font-medium text-amber-400 hover:text-amber-300"
            >
              + New Project
            </button>
          </div>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
            {projects.map((p) => {
              const isSelected = activeProject?.id === p.id;
              const thumbName = basenameFromPath(p.cover_thumbnail_path);
              const thumbUrl = thumbName ? apiUrl(`/api/media/project/${p.id}/thumbnails/${thumbName}`) : '';
              return (
                <div
                  key={p.id}
                  className={`rounded-xl border p-4 transition ${
                    isSelected
                      ? 'border-amber-500/60 bg-[#171d2c]'
                      : 'border-slate-800 bg-[#141926] hover:border-slate-700'
                  }`}
                >
                  <div className="relative mb-3 aspect-video overflow-hidden rounded-lg bg-slate-900 border border-slate-800 flex items-center justify-center">
                    {thumbUrl ? (
                      <img src={thumbUrl} alt={p.title} className="h-full w-full object-cover" />
                    ) : (
                      <div className="text-center text-xs text-slate-500">
                        <Film className="mx-auto mb-1 h-6 w-6 text-slate-600" />
                        {p.scene_count || 0} Storyboard Scenes
                      </div>
                    )}
                    <span className="absolute right-2 top-2 rounded bg-black/75 px-2 py-0.5 text-[11px] font-medium uppercase text-amber-300">
                      {p.language} • {p.resolution}
                    </span>
                  </div>
                  <h3 className="font-semibold text-white truncate">{p.title}</h3>
                  <p className="mt-0.5 text-xs text-slate-400 line-clamp-2">
                    {p.description || `${p.genre} • ${p.aspect_ratio} @ ${p.fps} FPS`}
                  </p>
                  <div className="mt-3 flex items-center justify-between text-xs text-slate-400">
                    <span>
                      {p.rendered_scene_count || 0}/{p.scene_count || 0} scenes rendered
                    </span>
                    <span
                      className={`rounded px-2 py-0.5 font-medium ${
                        p.export_status === 'completed'
                          ? 'bg-emerald-500/15 text-emerald-300'
                          : 'bg-slate-800 text-slate-300'
                      }`}
                    >
                      {p.export_status.replace(/_/g, ' ')}
                    </span>
                  </div>
                  <div className="mt-3 flex gap-2">
                    <button
                      onClick={() => onSelectProject(p.id, 'storyboard')}
                      className="flex-1 rounded-lg bg-amber-500/15 border border-amber-500/30 py-1.5 text-xs font-semibold text-amber-300 hover:bg-amber-500/25 transition"
                    >
                      Open Storyboard
                    </button>
                    {p.export_status === 'completed' && (
                      <button
                        onClick={() => onSelectProject(p.id, 'library')}
                        className="inline-flex items-center gap-1 rounded-lg bg-emerald-500/15 border border-emerald-500/30 px-3 py-1.5 text-xs font-semibold text-emerald-300 hover:bg-emerald-500/25"
                      >
                        <Play className="h-3.5 w-3.5" /> Watch
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Honest Feature & Hardware Transparency */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <div className="rounded-xl border border-slate-800 bg-[#111520] p-5">
          <h3 className="flex items-center gap-2 text-sm font-semibold text-white">
            <CheckCircle2 className="h-4 w-4 text-emerald-400" />
            Implemented &amp; Active Local Capabilities
          </h3>
          <ul className="mt-3 space-y-2 text-xs text-slate-300">
            <li>• <strong>Blender 4.2 LTS Cycles 3D Engine:</strong> Articulated humanoid character rigs, 12 environments, 20 keyframed animations, collision-safe combat choreography, and multi-shot cameras.</li>
            <li>• <strong>Offline Multilingual Speech &amp; Lip-Sync:</strong> Local eSpeak-NG C bridge supporting English, Urdu (اردو), and Roman Urdu normalization with frame-accurate 3D jaw viseme synchronization + optional Piper ONNX neural voice slot.</li>
            <li>• <strong>Original Procedural Sound Design:</strong> Ambience, weather, footsteps, sword/combat foley, ducked cinematic music, SRT/VTT subtitles, and verified H.264/AAC MP4 export.</li>
          </ul>
        </div>

        <div className="rounded-xl border border-slate-800 bg-[#111520] p-5">
          <h3 className="flex items-center gap-2 text-sm font-semibold text-white">
            <AlertTriangle className="h-4 w-4 text-amber-400" />
            Hardware Advisories &amp; Experimental Boundaries
          </h3>
          <ul className="mt-3 space-y-2 text-xs text-slate-300">
            {(hardware?.limitations || []).map((lim: string, i: number) => (
              <li key={i}>• {lim}</li>
            ))}
            <li>• <strong>Planned / Hardware-Gated:</strong> Multi-GB diffusion video models (Wan 2.1 / SVD-XT) require &ge;8–12 GB CUDA VRAM and are honestly gated when no discrete GPU is present.</li>
          </ul>
        </div>
      </div>
    </div>
  );
};

interface CreateProjectViewProps {
  voices: any[];
  musicMoods: any[];
  hardware: any;
  jobs: JobItem[];
  activeProject: ProjectSummary | null;
  onCreated: (project: ProjectSummary, navigateToStoryboard?: boolean) => Promise<void> | void;
  onJobQueued?: (job: JobItem) => void;
  onNavigate?: (nav: NavSection) => void;
}

function detectClientLanguageHint(text: string): { code: string; label: string } {
  const trimmed = text.trim();
  if (!trimmed) return { code: 'en', label: 'English (default)' };
  const urduMatches = trimmed.match(/[\u0600-\u06FF]/g) || [];
  if (urduMatches.length >= 6) return { code: 'ur', label: 'Urdu Script (اردو)' };
  const tokens = trimmed.toLowerCase().match(/[a-z']+/g) || [];
  const markers = new Set([
    'aur', 'hai', 'hain', 'tha', 'thi', 'mein', 'nahi', 'nahin', 'kya', 'lekin',
    'qila', 'qilay', 'qile', 'sipahi', 'darwaza', 'darwaze', 'larai', 'mukalma',
    'mehfooz', 'sardar', 'talwar', 'dushman', 'hum', 'tum', 'ek', 'ke', 'ka', 'ki',
  ]);
  let hits = 0;
  for (const t of tokens) {
    if (markers.has(t)) hits += 1;
  }
  if (hits >= 3 && tokens.length > 0 && hits / tokens.length >= 0.08) {
    return { code: 'roman_ur', label: 'Roman Urdu (Normalized to Urdu Speech)' };
  }
  return { code: 'en', label: 'English' };
}

export const CreateProjectView: React.FC<CreateProjectViewProps> = ({
  voices,
  musicMoods,
  hardware,
  jobs,
  activeProject,
  onCreated,
  onJobQueued,
  onNavigate,
}) => {
  const [samples, setSamples] = useState<Record<string, any>>({});
  const [title, setTitle] = useState('Guardians of the Crimson Fortress');
  const [description, setDescription] = useState('Historical sunset fortress drama with dialogue and sword combat.');
  const [language, setLanguage] = useState('auto');
  const [genre, setGenre] = useState('historical');
  const [visualStyle, setVisualStyle] = useState('cinematic_3d');
  const [historicalMode, setHistoricalMode] = useState(true);
  const [durationSec, setDurationSec] = useState(9);
  const [numScenes, setNumScenes] = useState(3);
  const [aspectRatio, setAspectRatio] = useState('16:9');
  const [resolution, setResolution] = useState('720p');
  const [fps, setFps] = useState(24);
  const [qualityProfile, setQualityProfile] = useState(hardware?.recommended_mode || 'low_resource');
  const [narratorVoice, setNarratorVoice] = useState('en_narrator_deep');
  const [narrationEnabled, setNarrationEnabled] = useState(true);
  const [subtitlesEnabled, setSubtitlesEnabled] = useState(true);
  const [burnCaptions, setBurnCaptions] = useState(true);
  const [musicMood, setMusicMood] = useState('epic_historical');
  const [scriptText, setScriptText] = useState('');
  const [warnings, setWarnings] = useState<string[]>([]);
  const [submittingMode, setSubmittingMode] = useState<'none' | 'storyboard' | 'video'>('none');
  const [err, setErr] = useState('');
  const [trackedJobId, setTrackedJobId] = useState<string | null>(null);
  const [trackedProjectId, setTrackedProjectId] = useState<string | null>(null);
  const [generatedVideo, setGeneratedVideo] = useState<any | null>(null);

  const detectedHint = detectClientLanguageHint(scriptText);
  const effectiveLangCode = language === 'auto' ? detectedHint.code : language;

  useEffect(() => {
    api.get('/api/projects/samples').then((d) => {
      setSamples(d.samples || {});
      if (!scriptText && d.samples?.en_historical_fortress) {
        setScriptText(d.samples.en_historical_fortress.script);
      }
    });
  }, []);

  useEffect(() => {
    if (language === 'auto') {
      setNarratorVoice(detectedHint.code === 'en' ? 'en_narrator_deep' : 'ur_narrator_deep');
    }
  }, [language, detectedHint.code]);

  useEffect(() => {
    api
      .post('/api/system/workload-check', {
        resolution,
        fps,
        duration_sec: durationSec,
        quality_profile: qualityProfile,
      })
      .then((d) => setWarnings(d.warnings || []))
      .catch(() => {});
  }, [resolution, fps, durationSec, qualityProfile]);

  const trackedJob: JobItem | undefined = trackedJobId
    ? jobs.find((j) => j.id === trackedJobId)
    : jobs.find((j) => j.project_id === (trackedProjectId || activeProject?.id) && j.job_type === 'render_full_project');

  useEffect(() => {
    const pid = trackedProjectId || trackedJob?.project_id || activeProject?.id;
    if (!pid) return;
    if (trackedJob?.status === 'completed' || (!trackedJob && activeProject?.export_status === 'completed')) {
      api
        .get('/api/library')
        .then((res) => {
          const match = (res.videos || []).find((v: any) => v.project_id === pid);
          if (match) setGeneratedVideo(match);
        })
        .catch(() => {});
    }
  }, [trackedJob?.status, trackedJob?.updated_at, trackedProjectId, activeProject?.id, activeProject?.export_status]);

  // Also poll job while running as fallback if WebSocket reconnects
  useEffect(() => {
    if (!trackedJobId) return;
    if (trackedJob && ['completed', 'failed', 'cancelled'].includes(trackedJob.status)) return;
    const timer = window.setInterval(async () => {
      try {
        const j = await api.get<JobItem>(`/api/jobs/${trackedJobId}`);
        if (onJobQueued) onJobQueued(j);
      } catch {
        // ignore transient poll error
      }
    }, 3000);
    return () => window.clearInterval(timer);
  }, [trackedJobId, trackedJob?.status]);

  const loadSample = (key: string) => {
    const s = samples[key];
    if (!s) return;
    setTitle(s.title);
    setDescription(s.description);
    setLanguage(s.language || 'auto');
    setGenre(s.genre || 'historical');
    setScriptText(s.script);
    setNarratorVoice(s.language === 'en' ? 'en_narrator_deep' : 'ur_narrator_deep');
  };

  const buildPayload = () => ({
    title,
    description,
    language,
    visual_style: visualStyle,
    genre,
    historical_accuracy_mode: historicalMode,
    target_duration_sec: durationSec,
    aspect_ratio: aspectRatio,
    resolution,
    fps,
    quality_profile: qualityProfile,
    num_scenes_target: numScenes,
    script_text: scriptText,
    narration_prefs: {
      enabled: narrationEnabled,
      voice_id:
        language === 'auto'
          ? effectiveLangCode === 'en'
            ? 'en_narrator_deep'
            : 'ur_narrator_deep'
          : narratorVoice,
    },
    dialogue_prefs: { enabled: true, subtitles: subtitlesEnabled, burn_in_captions: burnCaptions },
    music_prefs: { enabled: musicMood !== 'none', mood: musicMood, volume: 0.24 },
    auto_generate_storyboard: true,
  });

  const handleGenerateVideoNow = async (e: React.FormEvent) => {
    e.preventDefault();
    setErr('');
    setGeneratedVideo(null);
    setSubmittingMode('video');
    try {
      const created = await api.post<ProjectSummary>('/api/projects', buildPayload());
      setTrackedProjectId(created.id);
      await onCreated(created, false);
      const jobRes = await api.post<{ job: JobItem }>('/api/jobs/render-project', {
        project_id: created.id,
        force_rerender: true,
      });
      setTrackedJobId(jobRes.job.id);
      if (onJobQueued) onJobQueued(jobRes.job);
    } catch (ex: any) {
      setErr(ex.message || 'Failed to start video generation');
    } finally {
      setSubmittingMode('none');
    }
  };

  const handleCreateStoryboardOnly = async () => {
    setErr('');
    setSubmittingMode('storyboard');
    try {
      const created = await api.post<ProjectSummary>('/api/projects', buildPayload());
      await onCreated(created, true);
    } catch (ex: any) {
      setErr(ex.message || 'Failed to create project');
    } finally {
      setSubmittingMode('none');
    }
  };

  const isJobActive = trackedJob && (trackedJob.status === 'queued' || trackedJob.status === 'running' || trackedJob.status === 'paused');

  return (
    <div className="space-y-6">
      <form onSubmit={handleGenerateVideoNow} className="space-y-6">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 className="text-xl font-bold text-white">Create New 3D Video — Test Your Script</h2>
            <p className="text-xs text-slate-400">
              Paste your English, Roman Urdu, or Urdu (اردو) script, configure specs, and click <strong>Generate Video</strong> for end-to-end 3D MP4 creation, live progress, and instant playback.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            {samples.qila_pehli_jung && (
              <button
                type="button"
                onClick={() => loadSample('qila_pehli_jung')}
                className="rounded-lg border border-amber-500/40 bg-amber-500/15 px-3 py-1.5 text-xs font-semibold text-amber-300 hover:bg-amber-500/25"
              >
                Load Test Story: Qila Al-Noor
              </button>
            )}
            <button
              type="button"
              onClick={() => loadSample('en_historical_fortress')}
              className="rounded-lg border border-slate-700 bg-slate-800/80 px-3 py-1.5 text-xs text-slate-200 hover:bg-slate-700"
            >
              Load English Sample
            </button>
            <button
              type="button"
              onClick={() => loadSample('roman_ur_adventure')}
              className="rounded-lg border border-slate-700 bg-slate-800/80 px-3 py-1.5 text-xs text-slate-200 hover:bg-slate-700"
            >
              Load Roman Urdu Sample
            </button>
            <button
              type="button"
              onClick={() => loadSample('ur_cinematic_story')}
              className="rounded-lg border border-slate-700 bg-slate-800/80 px-3 py-1.5 text-xs text-slate-200 hover:bg-slate-700"
            >
              Load Urdu (اردو) Sample
            </button>
          </div>
        </div>

        {err && (
          <div className="flex items-start gap-2 rounded-lg border border-red-500/40 bg-red-500/10 p-3.5 text-xs text-red-200">
            <XCircle className="h-4 w-4 shrink-0 text-red-400 mt-0.5" />
            <div>
              <div className="font-semibold">Submission Error</div>
              <div>{err}</div>
            </div>
          </div>
        )}

      {warnings.length > 0 && (
        <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 p-3.5 text-xs text-amber-200 space-y-1">
          <div className="font-semibold flex items-center gap-1.5">
            <AlertTriangle className="h-4 w-4 text-amber-400" /> Hardware Workload Advisory
          </div>
          {warnings.map((w, idx) => (
            <div key={idx}>• {w}</div>
          ))}
        </div>
      )}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Left 2 Columns: Script & Story Metadata */}
        <div className="lg:col-span-2 space-y-4 rounded-xl border border-slate-800 bg-[#111520] p-5">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1">Story Title</label>
              <input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                required
                className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-white focus:border-amber-500 focus:outline-none"
              />
            </div>
            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="block text-xs font-medium text-slate-300">Language</label>
                {language === 'auto' && (
                  <span className="text-[11px] font-medium text-amber-300">
                    Detected: {detectedHint.label}
                  </span>
                )}
              </div>
              <select
                value={language}
                onChange={(e) => {
                  const v = e.target.value;
                  setLanguage(v);
                  if (v === 'roman_ur' || v === 'ur') setNarratorVoice('ur_narrator_deep');
                  else if (v === 'en') setNarratorVoice('en_narrator_deep');
                }}
                className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-white"
              >
                <option value="auto">Automatic Language Detection</option>
                <option value="en">English</option>
                <option value="roman_ur">Roman Urdu (Normalized to Urdu Speech &amp; Bilingual Subtitles)</option>
                <option value="ur">Urdu Script (اردو)</option>
              </select>
            </div>
          </div>

          <div>
            <label className="block text-xs font-medium text-slate-300 mb-1">Short Description</label>
            <input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-white"
            />
          </div>

          <div>
            <div className="flex items-center justify-between mb-1">
              <label className="text-xs font-medium text-slate-300">
                Story Script (Use `SCENE 1:` headers and `CHARACTER: dialogue` lines or narrative prose)
              </label>
              <span className="text-[11px] text-slate-500">{scriptText.length} chars</span>
            </div>
            <textarea
              value={scriptText}
              onChange={(e) => setScriptText(e.target.value)}
              dir={effectiveLangCode === 'ur' ? 'rtl' : 'ltr'}
              rows={13}
              required
              placeholder="Paste your original English, Roman Urdu, or Urdu story script here..."
              className="w-full rounded-lg border border-slate-700 bg-[#0b0e16] p-3.5 font-mono text-sm text-slate-100 focus:border-amber-500 focus:outline-none"
            />
          </div>
        </div>

        {/* Right Column: Render, Voice & Music Preferences */}
        <div className="space-y-4 rounded-xl border border-slate-800 bg-[#111520] p-5">
          <h3 className="text-sm font-semibold text-white border-b border-slate-800 pb-2">
            Visual, Audio &amp; Render Specs
          </h3>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-slate-400 mb-1">Genre</label>
              <select
                value={genre}
                onChange={(e) => setGenre(e.target.value)}
                className="w-full rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-2 text-xs text-white"
              >
                <option value="historical">Historical</option>
                <option value="adventure">Adventure</option>
                <option value="action">Action / Combat</option>
                <option value="fantasy">Fantasy</option>
                <option value="horror">Atmospheric Horror</option>
                <option value="educational">Educational</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">Visual Style</label>
              <select
                value={visualStyle}
                onChange={(e) => setVisualStyle(e.target.value)}
                className="w-full rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-2 text-xs text-white"
              >
                <option value="cinematic_3d">Cinematic 3D</option>
                <option value="stylized_epic">Stylized Epic 3D</option>
                <option value="dramatic_noir">Dramatic Chiaroscuro</option>
              </select>
            </div>
          </div>

          <div className="grid grid-cols-3 gap-2">
            <div>
              <label className="block text-xs text-slate-400 mb-1">Resolution</label>
              <select
                value={resolution}
                onChange={(e) => setResolution(e.target.value)}
                className="w-full rounded-lg border border-slate-700 bg-slate-900 px-2 py-2 text-xs text-white"
              >
                <option value="720p">720p HD</option>
                <option value="1080p">1080p FHD</option>
                <option value="1440p">1440p QHD</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">Aspect Ratio</label>
              <select
                value={aspectRatio}
                onChange={(e) => setAspectRatio(e.target.value)}
                className="w-full rounded-lg border border-slate-700 bg-slate-900 px-2 py-2 text-xs text-white"
              >
                <option value="16:9">16:9 Landscape</option>
                <option value="9:16">9:16 Portrait</option>
                <option value="1:1">1:1 Square</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">Frame Rate</label>
              <select
                value={fps}
                onChange={(e) => setFps(Number(e.target.value))}
                className="w-full rounded-lg border border-slate-700 bg-slate-900 px-2 py-2 text-xs text-white"
              >
                <option value={24}>24 FPS</option>
                <option value={30}>30 FPS</option>
                <option value={60}>60 FPS</option>
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs text-slate-400 mb-1">Target Duration (sec)</label>
              <input
                type="number"
                min={3}
                max={180}
                value={durationSec}
                onChange={(e) => setDurationSec(Number(e.target.value))}
                className="w-full rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-xs text-white"
              />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">Target Scenes</label>
              <input
                type="number"
                min={1}
                max={16}
                value={numScenes}
                onChange={(e) => setNumScenes(Number(e.target.value))}
                className="w-full rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-xs text-white"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs text-slate-400 mb-1">Quality &amp; Hardware Profile</label>
            <select
              value={qualityProfile}
              onChange={(e) => setQualityProfile(e.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-2 text-xs text-white"
            >
              <option value="low_resource">Low-Resource Mode (Fast CPU Raytrace)</option>
              <option value="balanced">Balanced Mode (Medium Cycles spp)</option>
              <option value="high_quality">High-Quality Mode (16 spp + Denoiser)</option>
              <option value="cinematic">Cinematic Mode (16 spp + OpenImageDenoise — Benchmarked Best Balance)</option>
            </select>
          </div>

          <div>
            <label className="block text-xs text-slate-400 mb-1">Narrator Voice</label>
            <select
              value={narratorVoice}
              onChange={(e) => setNarratorVoice(e.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-2 text-xs text-white"
            >
              {voices.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.name} ({v.language.toUpperCase()})
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs text-slate-400 mb-1">Background Music Score</label>
            <select
              value={musicMood}
              onChange={(e) => setMusicMood(e.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-900 px-2.5 py-2 text-xs text-white"
            >
              {musicMoods.map((m) => (
                <option key={m.id} value={m.id}>
                  {m.label}
                </option>
              ))}
            </select>
          </div>

          <div className="space-y-2 pt-1 text-xs text-slate-300">
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={historicalMode}
                onChange={(e) => setHistoricalMode(e.target.checked)}
                className="rounded border-slate-600"
              />
              Distinguish verified historical details from dramatized elements
            </label>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={narrationEnabled}
                onChange={(e) => setNarrationEnabled(e.target.checked)}
                className="rounded border-slate-600"
              />
              Enable scene voiceover narration when no dialogue is spoken
            </label>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={subtitlesEnabled}
                onChange={(e) => setSubtitlesEnabled(e.target.checked)}
                className="rounded border-slate-600"
              />
              Generate SRT/WebVTT subtitles &amp; captions
            </label>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={burnCaptions}
                onChange={(e) => setBurnCaptions(e.target.checked)}
                className="rounded border-slate-600"
              />
              Burn lower-third captions onto frames (Latin/Roman Urdu)
            </label>
          </div>

          <div className="space-y-2.5 pt-2">
            <button
              type="submit"
              disabled={submittingMode !== 'none' || Boolean(isJobActive)}
              className="w-full inline-flex items-center justify-center gap-2 rounded-lg bg-amber-500 py-2.5 px-4 text-sm font-bold text-slate-950 shadow hover:bg-amber-400 disabled:opacity-50 transition"
            >
              {submittingMode === 'video' ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" /> Starting 3D Render Pipeline...
                </>
              ) : isJobActive ? (
                <>
                  <Loader2 className="h-4 w-4 animate-spin" /> Rendering Video Below...
                </>
              ) : (
                <>
                  <Play className="h-4 w-4 fill-current" /> Generate Video
                </>
              )}
            </button>

            <button
              type="button"
              disabled={submittingMode !== 'none'}
              onClick={handleCreateStoryboardOnly}
              className="w-full rounded-lg border border-slate-700 bg-slate-800/80 py-2 px-3 text-xs font-semibold text-slate-200 hover:bg-slate-700 disabled:opacity-50 transition"
            >
              {submittingMode === 'storyboard'
                ? 'Analyzing Script & Building Storyboard...'
                : 'Create Storyboard Only (Customize Scenes First)'}
            </button>
          </div>
        </div>
      </div>
      </form>

      {/* Live Render Progress & Error Status Panel */}
      {trackedJob && (
        <div className="rounded-xl border border-slate-800 bg-[#111520] p-5 space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex items-center gap-2.5">
              {trackedJob.status === 'completed' ? (
                <CheckCircle2 className="h-5 w-5 text-emerald-400" />
              ) : trackedJob.status === 'failed' ? (
                <XCircle className="h-5 w-5 text-red-400" />
              ) : (
                <Loader2 className="h-5 w-5 animate-spin text-amber-400" />
              )}
              <div>
                <h3 className="text-sm font-bold text-white">
                  Video Generation Status:{' '}
                  <span className="uppercase text-amber-300">{trackedJob.status}</span>
                </h3>
                <p className="text-xs text-slate-400">
                  Stage: <strong className="text-slate-200">{trackedJob.current_stage}</strong> • Job ID:{' '}
                  <code className="text-slate-300">{trackedJob.id}</code>
                </p>
              </div>
            </div>
            {onNavigate && (
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={() => onNavigate('storyboard')}
                  className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-200 hover:bg-slate-700"
                >
                  Inspect Storyboard
                </button>
                <button
                  type="button"
                  onClick={() => onNavigate('queue')}
                  className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs text-slate-200 hover:bg-slate-700"
                >
                  Open Render Queue
                </button>
              </div>
            )}
          </div>

          {trackedJob.progress_measurable && trackedJob.progress_pct !== null ? (
            <div>
              <div className="flex justify-between text-xs text-slate-300 mb-1">
                <span>Measured 3D Pipeline Progress</span>
                <span className="font-semibold text-amber-300">{trackedJob.progress_pct}%</span>
              </div>
              <div className="h-2.5 w-full overflow-hidden rounded-full bg-slate-800">
                <div
                  className="h-full bg-gradient-to-r from-amber-500 to-emerald-400 transition-all duration-300"
                  style={{ width: `${Math.min(100, Math.max(2, trackedJob.progress_pct))}%` }}
                />
              </div>
            </div>
          ) : trackedJob.status === 'running' || trackedJob.status === 'queued' ? (
            <div className="rounded-lg border border-slate-800 bg-slate-900/70 px-3 py-2 text-xs text-slate-300">
              Active Stage (exact frame percentage not simulated during stream muxing):{' '}
              <strong className="text-amber-300">{trackedJob.current_stage}</strong>
            </div>
          ) : null}

          {trackedJob.error_details && (
            <div className="rounded-lg border border-red-500/40 bg-red-500/10 p-3 text-xs text-red-200">
              <strong>Render Error:</strong> {trackedJob.error_details}
            </div>
          )}

          {(trackedJob.logs || []).length > 0 && (
            <details className="text-xs">
              <summary className="cursor-pointer font-medium text-slate-400 hover:text-slate-200">
                View Live Render Telemetry Logs ({trackedJob.logs.length} entries)
              </summary>
              <pre className="mt-2 max-h-40 overflow-y-auto rounded-lg border border-slate-800 bg-[#090c14] p-3 font-mono text-[11px] text-slate-300">
                {trackedJob.logs.slice(-18).join('\n')}
              </pre>
            </details>
          )}
        </div>
      )}

      {/* Inline Generated Video Player + MP4 & SRT/VTT Subtitle Downloads */}
      {generatedVideo && (
        <div className="rounded-xl border border-emerald-500/35 bg-[#111520] p-5 space-y-4 shadow-lg">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="inline-flex items-center gap-1.5 rounded-full bg-emerald-500/15 px-2.5 py-0.5 text-[11px] font-semibold text-emerald-300">
                <CheckCircle2 className="h-3.5 w-3.5" /> PyAV Stream &amp; Frame Decode Verified
              </div>
              <h3 className="mt-1 text-lg font-bold text-white">{generatedVideo.title}</h3>
              <p className="text-xs text-slate-400">
                {generatedVideo.resolution} • {generatedVideo.fps} FPS • {generatedVideo.duration_sec}s •{' '}
                {generatedVideo.file_size_mb} MB • H.264 + AAC Stereo
              </p>
            </div>

            <div className="flex flex-wrap gap-2">
              <a
                href={generatedVideo.download_url}
                download
                className="inline-flex items-center gap-1.5 rounded-lg bg-amber-500 px-3.5 py-2 text-xs font-bold text-slate-950 hover:bg-amber-400 transition"
              >
                <Download className="h-4 w-4" /> Download MP4
              </a>
              {generatedVideo.subtitle_srt_url && (
                <a
                  href={generatedVideo.subtitle_srt_url}
                  download
                  className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-xs font-semibold text-slate-200 hover:bg-slate-700"
                >
                  <FileText className="h-3.5 w-3.5 text-amber-400" /> Download SRT
                </a>
              )}
              {generatedVideo.subtitle_vtt_url && (
                <a
                  href={`${generatedVideo.subtitle_vtt_url}?download=1`}
                  download
                  className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-xs font-semibold text-slate-200 hover:bg-slate-700"
                >
                  <FileText className="h-3.5 w-3.5 text-sky-400" /> Download VTT
                </a>
              )}
              {generatedVideo.subtitle_ur_srt_url && (
                <a
                  href={generatedVideo.subtitle_ur_srt_url}
                  download
                  className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-xs font-semibold text-emerald-200 hover:bg-emerald-500/20"
                >
                  <FileText className="h-3.5 w-3.5 text-emerald-400" /> Download Urdu (اردو) SRT
                </a>
              )}
            </div>
          </div>

          <video
            key={generatedVideo.video_url + generatedVideo.updated_at}
            controls
            className="w-full max-h-[440px] rounded-lg bg-black border border-slate-800"
            src={`${generatedVideo.video_url}?t=${encodeURIComponent(generatedVideo.updated_at)}`}
          >
            {generatedVideo.subtitle_vtt_url && (
              <track
                kind="subtitles"
                src={generatedVideo.subtitle_vtt_url}
                srcLang={generatedVideo.language || 'en'}
                label={generatedVideo.language === 'roman_ur' ? 'Roman Urdu Subtitles' : 'Subtitles'}
                default
              />
            )}
            {generatedVideo.subtitle_ur_vtt_url && (
              <track
                kind="subtitles"
                src={generatedVideo.subtitle_ur_vtt_url}
                srcLang="ur"
                label="Urdu (اردو) Subtitles"
              />
            )}
          </video>
        </div>
      )}
    </div>
  );
};
