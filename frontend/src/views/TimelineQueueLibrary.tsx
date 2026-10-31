import React, { useEffect, useState } from 'react';
import {
  ArrowLeft,
  ArrowRight,
  Play,
  Pause,
  RotateCcw,
  XCircle,
  Download,
  Film,
  Search,
  Volume2,
  Subtitles,
  CheckSquare,
  Square,
  FileText,
} from 'lucide-react';
import { api, apiUrl, basenameFromPath } from '../api';
import { JobItem, NavSection, ProjectSummary, SceneItem } from '../types';

/* ==================== SCENE TIMELINE ==================== */
export const SceneTimelineView: React.FC<{
  project: ProjectSummary | null;
  onRefreshProject: () => Promise<void>;
  onRenderSelected: (sceneIds: string[]) => Promise<void>;
  onRenderFull: (forceRerender?: boolean) => Promise<void>;
  onNavigate: (nav: NavSection) => void;
}> = ({ project, onRefreshProject, onRenderSelected, onRenderFull, onNavigate }) => {
  const [selectedIds, setSelectedIds] = useState<string[]>([]);
  const [activeClipUrl, setActiveClipUrl] = useState<string>('');

  if (!project) {
    return (
      <div className="rounded-xl border border-slate-800 bg-[#111520] p-8 text-center text-sm text-slate-400">
        Select or create a project to open the multi-track Scene Timeline.
      </div>
    );
  }

  const scenes = project.scenes || [];
  const totalDur = scenes.reduce((acc, s) => acc + Number(s.duration_sec || 0), 0);

  const moveScene = async (idx: number, dir: -1 | 1) => {
    const targetIdx = idx + dir;
    if (targetIdx < 0 || targetIdx >= scenes.length) return;
    const ids = scenes.map((s) => s.id);
    const [removed] = ids.splice(idx, 1);
    ids.splice(targetIdx, 0, removed);
    await api.post(`/api/projects/${project.id}/scenes/reorder`, { ordered_scene_ids: ids });
    await onRefreshProject();
  };

  const toggleSelect = (id: string) => {
    setSelectedIds((prev) => (prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]));
  };

  const updateAudioCue = async (sc: SceneItem, key: string, val: any) => {
    await api.patch(`/api/projects/${project.id}/scenes/${sc.id}`, {
      audio_cues: { ...(sc.audio_cues || {}), [key]: val },
    });
    await onRefreshProject();
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold text-white">Scene Timeline &amp; Multi-Track Mixer</h2>
          <p className="text-xs text-slate-400">
            Total Chronological Runtime: <strong className="text-amber-300">{totalDur.toFixed(1)}s</strong> across{' '}
            {scenes.length} scene(s) • Save Status: <strong className="text-emerald-400">{project.save_status}</strong>
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {selectedIds.length > 0 && (
            <button
              onClick={() => onRenderSelected(selectedIds)}
              className="rounded-lg border border-amber-500/40 bg-amber-500/20 px-3 py-2 text-xs font-semibold text-amber-300 hover:bg-amber-500/30"
            >
              Render {selectedIds.length} Selected Scene(s)
            </button>
          )}
          <button
            onClick={() => onRenderFull(false)}
            className="inline-flex items-center gap-1.5 rounded-lg bg-amber-500 px-4 py-2 text-xs font-bold text-slate-950 hover:bg-amber-400"
          >
            <Film className="h-4 w-4" /> Export Full Chronological MP4
          </button>
        </div>
      </div>

      {activeClipUrl && (
        <div className="rounded-xl border border-amber-500/40 bg-[#111520] p-4">
          <div className="flex justify-between items-center mb-2 text-xs">
            <span className="font-semibold text-amber-300">Timeline Clip Monitor</span>
            <button onClick={() => setActiveClipUrl('')} className="text-slate-400 hover:text-white">
              Close
            </button>
          </div>
          <video src={activeClipUrl} controls autoPlay className="mx-auto max-h-72 rounded-lg bg-black" />
        </div>
      )}

      {/* Horizontal Visual Sequence Strip */}
      <div className="overflow-x-auto rounded-xl border border-slate-800 bg-[#111520] p-4">
        <div className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-3">
          Video, Camera &amp; Transition Track
        </div>
        <div className="flex gap-3 min-w-max">
          {scenes.map((sc, idx) => {
            const isSel = selectedIds.includes(sc.id);
            const clipFile = basenameFromPath(sc.rendered_video_path);
            const clipUrl = clipFile ? apiUrl(`/api/media/project/${project.id}/renders/${clipFile}`) : '';
            return (
              <div
                key={sc.id}
                style={{ width: `${Math.max(230, Math.round(sc.duration_sec * 42))}px` }}
                className={`rounded-lg border p-3 flex flex-col gap-2 ${
                  isSel ? 'border-amber-500 bg-[#1a2032]' : 'border-slate-800 bg-[#151a28]'
                }`}
              >
                <div className="flex items-center justify-between text-xs">
                  <button
                    onClick={() => toggleSelect(sc.id)}
                    className="inline-flex items-center gap-1.5 font-semibold text-white"
                  >
                    {isSel ? <CheckSquare className="h-3.5 w-3.5 text-amber-400" /> : <Square className="h-3.5 w-3.5 text-slate-500" />}
                    #{idx + 1} {sc.title.slice(0, 20)}
                  </button>
                  <span className="text-amber-300 font-mono">{sc.duration_sec}s</span>
                </div>

                <div className="text-[11px] text-slate-400">
                  Cam: {sc.camera_shot} • Trans: {sc.transition_type}
                </div>

                {/* Dialogue & Subtitle Track Mini-Bars */}
                <div className="rounded bg-sky-500/10 border border-sky-500/20 px-2 py-1 text-[11px] text-sky-200 truncate">
                  <Subtitles className="inline h-3 w-3 mr-1" />
                  {sc.dialogue.length > 0
                    ? `${sc.dialogue.length} dialogue line(s)`
                    : sc.narration_text
                    ? 'Narrator VO'
                    : 'Action / Foley only'}
                </div>

                <div className="rounded bg-purple-500/10 border border-purple-500/20 px-2 py-1 text-[11px] text-purple-200 flex items-center justify-between">
                  <span>
                    <Volume2 className="inline h-3 w-3 mr-1" />
                    {sc.audio_cues?.music_mood || 'epic_historical'}
                  </span>
                  <label className="inline-flex items-center gap-1 text-[10px]">
                    <input
                      type="checkbox"
                      checked={Boolean(sc.audio_cues?.dialogue_ducking ?? true)}
                      onChange={(e) => updateAudioCue(sc, 'dialogue_ducking', e.target.checked)}
                    />
                    Duck
                  </label>
                </div>

                <div className="mt-auto flex items-center justify-between pt-1">
                  <div className="flex gap-1">
                    <button
                      disabled={idx === 0}
                      onClick={() => moveScene(idx, -1)}
                      className="rounded bg-slate-800 p-1 text-slate-300 hover:bg-slate-700 disabled:opacity-30"
                      title="Move Earlier"
                    >
                      <ArrowLeft className="h-3.5 w-3.5" />
                    </button>
                    <button
                      disabled={idx === scenes.length - 1}
                      onClick={() => moveScene(idx, 1)}
                      className="rounded bg-slate-800 p-1 text-slate-300 hover:bg-slate-700 disabled:opacity-30"
                      title="Move Later"
                    >
                      <ArrowRight className="h-3.5 w-3.5" />
                    </button>
                  </div>
                  {clipUrl && sc.generation_status === 'completed' ? (
                    <button
                      onClick={() => setActiveClipUrl(`${clipUrl}?t=${encodeURIComponent(sc.updated_at || '')}`)}
                      className="inline-flex items-center gap-1 rounded bg-emerald-500/20 px-2 py-1 text-[11px] text-emerald-300"
                    >
                      <Play className="h-3 w-3" /> Preview
                    </button>
                  ) : (
                    <span className="text-[11px] text-slate-500">{sc.generation_status}</span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};

/* ==================== RENDER QUEUE ==================== */
export const RenderQueueView: React.FC<{
  jobs: JobItem[];
  wsConnected: boolean;
  onRefreshJobs: () => Promise<void>;
}> = ({ jobs, wsConnected, onRefreshJobs }) => {
  const [expandedJobId, setExpandedJobId] = useState<string | null>(jobs[0]?.id || null);

  const controlJob = async (jobId: string, action: 'pause' | 'resume' | 'cancel' | 'retry') => {
    await api.post(`/api/jobs/${jobId}/${action}`);
    await onRefreshJobs();
  };

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-white">Background Render Queue &amp; Live Telemetry</h2>
          <p className="text-xs text-slate-400">
            Real measurable Blender frame counts &amp; FFmpeg stream verification. Percentages are never simulated.
          </p>
        </div>
        <span
          className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium ${
            wsConnected ? 'bg-emerald-500/15 text-emerald-300' : 'bg-amber-500/15 text-amber-300'
          }`}
        >
          <span className={`h-2 w-2 rounded-full ${wsConnected ? 'bg-emerald-400' : 'bg-amber-400'}`} />
          {wsConnected ? 'WebSocket Live' : 'Polling Fallback'}
        </span>
      </div>

      {jobs.length === 0 ? (
        <div className="rounded-xl border border-slate-800 bg-[#111520] p-8 text-center text-sm text-slate-400">
          No render jobs queued yet. Render a scene or full project from Storyboard or Timeline.
        </div>
      ) : (
        <div className="space-y-3">
          {jobs.map((job) => {
            const isExpanded = expandedJobId === job.id;
            return (
              <div key={job.id} className="rounded-xl border border-slate-800 bg-[#121723] p-4 space-y-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs text-amber-300">{job.id}</span>
                      <span className="text-sm font-semibold text-white">{job.job_type.replace(/_/g, ' ')}</span>
                      <span
                        className={`rounded-full px-2.5 py-0.5 text-[11px] font-semibold ${
                          job.status === 'completed'
                            ? 'bg-emerald-500/15 text-emerald-300'
                            : job.status === 'failed'
                            ? 'bg-red-500/15 text-red-300'
                            : job.status === 'running'
                            ? 'bg-sky-500/15 text-sky-300'
                            : 'bg-slate-800 text-slate-300'
                        }`}
                      >
                        {job.status}
                      </span>
                    </div>
                    <div className="mt-1 text-xs text-slate-300">Stage: {job.current_stage}</div>
                  </div>

                  <div className="flex items-center gap-2">
                    {job.status === 'running' && job.worker_pid && (
                      <button
                        onClick={() => controlJob(job.id, 'pause')}
                        className="inline-flex items-center gap-1 rounded bg-slate-800 px-2.5 py-1 text-xs text-slate-200 hover:bg-slate-700"
                      >
                        <Pause className="h-3.5 w-3.5" /> Pause
                      </button>
                    )}
                    {job.status === 'paused' && (
                      <button
                        onClick={() => controlJob(job.id, 'resume')}
                        className="inline-flex items-center gap-1 rounded bg-emerald-500/20 px-2.5 py-1 text-xs text-emerald-300"
                      >
                        <Play className="h-3.5 w-3.5" /> Resume
                      </button>
                    )}
                    {(job.status === 'running' || job.status === 'queued' || job.status === 'paused') && (
                      <button
                        onClick={() => controlJob(job.id, 'cancel')}
                        className="inline-flex items-center gap-1 rounded bg-red-500/20 px-2.5 py-1 text-xs text-red-300 hover:bg-red-500/30"
                      >
                        <XCircle className="h-3.5 w-3.5" /> Cancel
                      </button>
                    )}
                    {(job.status === 'failed' || job.status === 'cancelled' || job.status === 'interrupted') && (
                      <button
                        onClick={() => controlJob(job.id, 'retry')}
                        className="inline-flex items-center gap-1 rounded bg-amber-500/20 px-2.5 py-1 text-xs text-amber-300 hover:bg-amber-500/30"
                      >
                        <RotateCcw className="h-3.5 w-3.5" /> Retry
                      </button>
                    )}
                    <button
                      onClick={() => setExpandedJobId(isExpanded ? null : job.id)}
                      className="rounded border border-slate-700 px-2.5 py-1 text-xs text-slate-300 hover:bg-slate-800"
                    >
                      {isExpanded ? 'Hide Logs' : 'Logs'}
                    </button>
                  </div>
                </div>

                {/* Honest Progress Indicator */}
                {job.progress_measurable && job.progress_pct !== null ? (
                  <div>
                    <div className="flex justify-between text-[11px] text-slate-400 mb-1">
                      <span>Measured Frame/Scene Progress</span>
                      <span>{job.progress_pct.toFixed(1)}%</span>
                    </div>
                    <div className="h-2 w-full overflow-hidden rounded-full bg-slate-900">
                      <div
                        style={{ width: `${Math.min(100, Math.max(0, job.progress_pct))}%` }}
                        className="h-full bg-amber-500 transition-all duration-300"
                      />
                    </div>
                  </div>
                ) : job.status === 'running' ? (
                  <div className="text-[11px] text-sky-300">
                    Active stage in progress (unmeasurable sub-step — exact stage shown above)
                  </div>
                ) : null}

                {job.error_details && (
                  <div className="rounded border border-red-500/30 bg-red-500/10 p-2.5 text-xs text-red-200">
                    Failure Reason: {job.error_details}
                  </div>
                )}

                {isExpanded && (
                  <pre className="max-h-48 overflow-y-auto rounded-lg bg-[#080b12] p-3 font-mono text-[11px] text-slate-300 border border-slate-800">
                    {(job.logs || []).join('\n')}
                  </pre>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

/* ==================== VIDEO LIBRARY ==================== */
export const VideoLibraryView: React.FC = () => {
  const [videos, setVideos] = useState<any[]>([]);
  const [search, setSearch] = useState('');
  const [sortBy, setSortBy] = useState('newest');
  const [activeVideo, setActiveVideo] = useState<any | null>(null);

  const loadLibrary = async () => {
    const res = await api.get(`/api/library?search=${encodeURIComponent(search)}&sort_by=${sortBy}`);
    const list = res.videos || [];
    setVideos(list);
    if (list.length > 0 && !activeVideo) {
      setActiveVideo(list[0]);
    }
  };

  useEffect(() => {
    loadLibrary();
  }, [search, sortBy]);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold text-white">Verified Video Library &amp; Render Reports</h2>
          <p className="text-xs text-slate-400">
            Every video listed here has passed PyAV H.264 video + AAC audio stream decode verification.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-2.5 h-3.5 w-3.5 text-slate-500" />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search videos..."
              className="rounded-lg border border-slate-700 bg-slate-900 pl-8 pr-3 py-1.5 text-xs text-white"
            />
          </div>
          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value)}
            className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs text-white"
          >
            <option value="newest">Newest First</option>
            <option value="duration">Longest Duration</option>
            <option value="size">Largest File Size</option>
            <option value="title">Title (A-Z)</option>
          </select>
        </div>
      </div>

      {videos.length === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-700 bg-[#111520] p-10 text-center text-sm text-slate-400">
          No exported MP4 videos match your filter yet. Render a project from Storyboard or Timeline to populate your library!
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          {/* Theater Player & Render Report */}
          {activeVideo && (
            <div className="lg:col-span-2 space-y-4 rounded-xl border border-slate-800 bg-[#111520] p-5">
              <video
                key={activeVideo.video_url + activeVideo.updated_at}
                controls
                className="w-full max-h-[420px] rounded-lg bg-black border border-slate-800"
                src={`${activeVideo.video_url}?t=${encodeURIComponent(activeVideo.updated_at)}`}
              >
                {activeVideo.subtitle_vtt_url && (
                  <track
                    kind="subtitles"
                    src={activeVideo.subtitle_vtt_url}
                    srcLang={activeVideo.language}
                    label={activeVideo.language === 'roman_ur' ? 'Roman Urdu Subtitles' : 'Subtitles'}
                    default
                  />
                )}
                {activeVideo.subtitle_ur_vtt_url && (
                  <track
                    kind="subtitles"
                    src={activeVideo.subtitle_ur_vtt_url}
                    srcLang="ur"
                    label="Urdu (اردو) Subtitles"
                  />
                )}
              </video>

              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <h3 className="text-lg font-bold text-white">{activeVideo.title}</h3>
                  <div className="text-xs text-slate-400">
                    {activeVideo.resolution} • {activeVideo.fps} FPS • {activeVideo.duration_sec}s •{' '}
                    {activeVideo.file_size_mb} MB
                  </div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <a
                    href={activeVideo.download_url}
                    download
                    className="inline-flex items-center gap-2 rounded-lg bg-amber-500 px-4 py-2 text-xs font-bold text-slate-950 hover:bg-amber-400"
                  >
                    <Download className="h-4 w-4" /> Download Verified MP4
                  </a>
                  {activeVideo.subtitle_srt_url && (
                    <a
                      href={activeVideo.subtitle_srt_url}
                      download
                      className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-xs font-semibold text-slate-200 hover:bg-slate-700"
                    >
                      <FileText className="h-3.5 w-3.5 text-amber-400" /> SRT
                    </a>
                  )}
                  {activeVideo.subtitle_vtt_url && (
                    <a
                      href={`${activeVideo.subtitle_vtt_url}?download=1`}
                      download
                      className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-xs font-semibold text-slate-200 hover:bg-slate-700"
                    >
                      <FileText className="h-3.5 w-3.5 text-sky-400" /> VTT
                    </a>
                  )}
                  {activeVideo.subtitle_ur_srt_url && (
                    <a
                      href={activeVideo.subtitle_ur_srt_url}
                      download
                      className="inline-flex items-center gap-1.5 rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-xs font-semibold text-emerald-200 hover:bg-emerald-500/20"
                    >
                      <FileText className="h-3.5 w-3.5 text-emerald-400" /> Urdu SRT
                    </a>
                  )}
                </div>
              </div>

              {/* Render Report */}
              {activeVideo.render_report && (
                <div className="rounded-lg border border-slate-800 bg-[#0c101a] p-4 text-xs space-y-2">
                  <div className="flex items-center gap-1.5 font-semibold text-amber-300">
                    <FileText className="h-4 w-4" /> Final Render Verification Report
                  </div>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-slate-300">
                    <div>File: <strong>{activeVideo.render_report.output_filename}</strong></div>
                    <div>Audio: <strong>{activeVideo.render_report.audio_status}</strong></div>
                    <div>Render Time: <strong>{activeVideo.render_report.render_time_sec}s</strong></div>
                    <div>
                      Scenes: <strong>{activeVideo.render_report.scenes_included}/{activeVideo.render_report.scenes_total}</strong>
                    </div>
                  </div>
                  {(activeVideo.render_report.warnings || []).length > 0 && (
                    <div className="text-amber-200/90 space-y-0.5 pt-1">
                      {activeVideo.render_report.warnings.map((w: string, i: number) => (
                        <div key={i}>• Advisory: {w}</div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Video Cards List */}
          <div className="space-y-3">
            {videos.map((v) => (
              <div
                key={v.project_id}
                onClick={() => setActiveVideo(v)}
                className={`cursor-pointer rounded-xl border p-3 transition ${
                  activeVideo?.project_id === v.project_id
                    ? 'border-amber-500 bg-[#182032]'
                    : 'border-slate-800 bg-[#121723] hover:border-slate-700'
                }`}
              >
                <div className="flex gap-3">
                  {v.thumbnail_url ? (
                    <img src={v.thumbnail_url} alt={v.title} className="h-16 w-28 rounded object-cover shrink-0" />
                  ) : (
                    <div className="h-16 w-28 rounded bg-slate-900 shrink-0" />
                  )}
                  <div className="min-w-0">
                    <div className="font-semibold text-sm text-white truncate">{v.title}</div>
                    <div className="text-[11px] text-slate-400">
                      {v.resolution} • {v.duration_sec}s • {v.file_size_mb} MB
                    </div>
                    <div className="mt-1 text-[10px] uppercase text-amber-300">{v.language}</div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};
