import React, { useEffect, useMemo, useState } from 'react';
import {
  Braces,
  ChevronDown,
  ChevronUp,
  Clapperboard,
  Download,
  Eye,
  FileText,
  Film,
  Hammer,
  ListChecks,
  Play,
  RefreshCw,
  RotateCcw,
  Sparkles,
  Volume2,
  XCircle,
} from 'lucide-react';
import { api, apiUrl } from '../api';
import {
  JobItem,
  MotionAutoPreview,
  MotionJobMode,
  MotionJobQuality,
  MotionPreview,
  MotionSelectionId,
  MotionTemplateInfo,
} from '../types';

const SAMPLE_SCRIPT = [
  "Bilal qile mein aata hai. Zara mash'al jalati hai. Dono baat karte hain.",
  '',
  "Bilal kehta hai: 'Guard your left flank!' Zara kehti hai: 'Ready!'",
].join('\n');

function statusClasses(status: string): string {
  if (status === 'completed') return 'bg-emerald-500/15 text-emerald-300';
  if (status === 'failed') return 'bg-red-500/15 text-red-300';
  if (status === 'running') return 'bg-sky-500/15 text-sky-300';
  if (status === 'paused') return 'bg-amber-500/15 text-amber-300';
  if (status === 'cancelled' || status === 'interrupted') return 'bg-orange-500/15 text-orange-300';
  return 'bg-slate-800 text-slate-300';
}

export const MotionStudioView: React.FC<{
  jobs: JobItem[];
  wsConnected: boolean;
  onJobUpdated: (job: JobItem) => void;
  onNotify: (message: string) => void;
  onOpenQueue: () => void;
}> = ({ jobs, wsConnected, onJobUpdated, onNotify, onOpenQueue }) => {
  const [templates, setTemplates] = useState<MotionTemplateInfo[]>([]);
  const [template, setTemplate] = useState<MotionSelectionId>('auto');
  const [mode, setMode] = useState<MotionJobMode>('render');
  const [fps, setFps] = useState<24 | 30 | 60>(30);
  const [quality, setQuality] = useState<MotionJobQuality>('standard');
  const [includeDialogueAudio, setIncludeDialogueAudio] = useState(false);
  const [scriptText, setScriptText] = useState(SAMPLE_SCRIPT);
  const [requestText, setRequestText] = useState('{}');
  const [preview, setPreview] = useState<MotionPreview | MotionAutoPreview | null>(null);
  const [error, setError] = useState('');
  const [busyPreview, setBusyPreview] = useState(false);
  const [busySubmit, setBusySubmit] = useState(false);
  const [expandedJobId, setExpandedJobId] = useState<string | null>(null);

  const selectedTemplate = useMemo(
    () => templates.find((item) => item.id === template),
    [templates, template]
  );
  const motionJobs = useMemo(
    () => jobs.filter((job) => job.job_type === 'motion_graphics'),
    [jobs]
  );
  const isAuto = template === 'auto';

  useEffect(() => {
    api
      .get('/api/jobs/motion-graphics/templates')
      .then((res) => setTemplates(res.templates || []))
      .catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, []);

  useEffect(() => {
    if (!expandedJobId && motionJobs[0]) setExpandedJobId(motionJobs[0].id);
  }, [expandedJobId, motionJobs]);

  const buildPayload = () => {
    if (isAuto) {
      return {
        script_text: scriptText,
        mode,
        fps,
        quality,
        brand_label: 'SIDD STUDIO',
        include_dialogue_audio: mode === 'render' && includeDialogueAudio,
      };
    }

    let request: Record<string, any>;
    try {
      request = requestText.trim() ? JSON.parse(requestText) : {};
    } catch (err) {
      throw new Error(`Request overrides are not valid JSON: ${err instanceof Error ? err.message : String(err)}`);
    }
    if (!request || Array.isArray(request) || typeof request !== 'object') {
      throw new Error('Request overrides must be a JSON object.');
    }
    return {
      template,
      request,
      script_text: scriptText,
      mode,
      fps,
      quality,
    };
  };

  const handlePreview = async () => {
    setBusyPreview(true);
    setError('');
    try {
      const result = isAuto
        ? await api.post<MotionAutoPreview>(
            '/api/jobs/motion-graphics/auto/preview',
            buildPayload()
          )
        : await api.post<MotionPreview>(
            '/api/jobs/motion-graphics/preview',
            buildPayload()
          );
      setPreview(result);
      onNotify('Motion Studio preview validated locally.');
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusyPreview(false);
    }
  };

  const handleQueue = async () => {
    setBusySubmit(true);
    setError('');
    try {
      const result = await api.post(
        isAuto ? '/api/jobs/motion-graphics/auto' : '/api/jobs/motion-graphics',
        buildPayload()
      );
      if (result.job) {
        onJobUpdated(result.job as JobItem);
        setExpandedJobId(result.job.id);
      }
      if (result.preview) {
        setPreview(
          isAuto
            ? (result.preview as MotionAutoPreview)
            : (result.preview as MotionPreview)
        );
      }
      onNotify(
        isAuto
          ? mode === 'render'
            ? includeDialogueAudio
              ? 'Auto-mapper video with local dialogue audio queued. The voice MP4 will appear in the inline player below.'
              : 'Auto-mapper video queued. The combined MP4 will appear in the inline player below.'
            : 'Auto-mapper build-only job queued.'
          : mode === 'render'
            ? 'Motion-graphics render queued. Live progress will appear below.'
            : 'Motion-graphics build-only job queued.'
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusySubmit(false);
    }
  };

  const controlJob = async (jobId: string, action: 'pause' | 'resume' | 'cancel' | 'retry') => {
    setError('');
    try {
      const updated = await api.post<JobItem>(`/api/jobs/${jobId}/${action}`);
      onJobUpdated(updated);
      onNotify(`Job ${jobId}: ${action} requested.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const selectTemplate = (id: MotionSelectionId) => {
    setTemplate(id);
    setRequestText('{}');
    setPreview(null);
    setError('');
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="inline-flex items-center gap-2 rounded-full border border-amber-500/30 bg-amber-500/10 px-3 py-1 text-[11px] font-bold tracking-widest text-amber-300">
            <Sparkles className="h-3.5 w-3.5" /> AUTO-MAPPER · LOCAL HYPERFRAMES JOBS
          </div>
          <h2 className="mt-3 text-2xl font-black tracking-tight text-white">Motion Studio</h2>
          <p className="mt-1 max-w-3xl text-sm text-slate-400">
            In Auto mode, paste a script and the deterministic planner maps each parsed scene to
            Title, Quote, Data or Outro clips, renders them locally, joins them, and verifies one
            playable/downloadable MP4. Manual templates remain available below.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium ${
              wsConnected ? 'bg-emerald-500/15 text-emerald-300' : 'bg-amber-500/15 text-amber-300'
            }`}
          >
            <span className={`h-2 w-2 rounded-full ${wsConnected ? 'bg-emerald-400' : 'bg-amber-400'}`} />
            {wsConnected ? 'Job stream live' : 'Job stream reconnecting'}
          </span>
          <button
            onClick={onOpenQueue}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs font-semibold text-slate-200 hover:bg-slate-800"
          >
            <ListChecks className="h-4 w-4" /> Render Queue
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-xl border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-200">
          {error}
        </div>
      )}

      <div className="grid gap-5 xl:grid-cols-[minmax(0,1.15fr)_minmax(360px,0.85fr)]">
        <section className="space-y-5 rounded-2xl border border-slate-800 bg-[#111520] p-5">
          <div>
            <div className="mb-3 flex items-center gap-2 text-sm font-bold text-white">
              <Clapperboard className="h-4 w-4 text-amber-400" /> 1. Choose Auto or a manual template
            </div>
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6">
              <button
                onClick={() => selectTemplate('auto')}
                className={`rounded-xl border p-3 text-left transition ${
                  isAuto
                    ? 'border-amber-500/70 bg-amber-500/15 text-amber-100'
                    : 'border-slate-800 bg-slate-950/40 text-slate-300 hover:border-slate-600'
                }`}
              >
                <div className="flex items-center gap-1.5 text-xs font-extrabold uppercase tracking-wider">
                  <Sparkles className="h-3.5 w-3.5" /> Auto
                </div>
                <div className="mt-1 line-clamp-3 text-[11px] leading-relaxed text-slate-400">
                  Script → scene mapping → multiple clips → combined MP4.
                </div>
                <div className="mt-2 font-mono text-[10px] text-slate-500">scene-led hybrid</div>
              </button>
              {templates.map((item) => {
                const active = item.id === template;
                return (
                  <button
                    key={item.id}
                    onClick={() => selectTemplate(item.id)}
                    className={`rounded-xl border p-3 text-left transition ${
                      active
                        ? 'border-amber-500/70 bg-amber-500/15 text-amber-100'
                        : 'border-slate-800 bg-slate-950/40 text-slate-300 hover:border-slate-600'
                    }`}
                  >
                    <div className="text-xs font-extrabold uppercase tracking-wider">{item.label}</div>
                    <div className="mt-1 line-clamp-3 text-[11px] leading-relaxed text-slate-400">
                      {item.description}
                    </div>
                    <div className="mt-2 font-mono text-[10px] text-slate-500">
                      {String(item.default_request.duration_sec ?? '—')}s default
                    </div>
                  </button>
                );
              })}
            </div>
            {isAuto ? (
              <div className="mt-3 flex flex-wrap gap-1.5">
                {[
                  'dialogue → quote',
                  '2+ numbers → data',
                  'narrative/action → title',
                  'final closing cue → outro',
                  'parser order',
                ].map((rule) => (
                  <span key={rule} className="rounded-full bg-slate-800 px-2 py-1 font-mono text-[10px] text-slate-400">
                    {rule}
                  </span>
                ))}
              </div>
            ) : selectedTemplate ? (
              <div className="mt-3 flex flex-wrap gap-1.5">
                {selectedTemplate.request_fields.map((field) => (
                  <span key={field} className="rounded-full bg-slate-800 px-2 py-1 font-mono text-[10px] text-slate-400">
                    {field}
                  </span>
                ))}
              </div>
            ) : null}
          </div>

          <div>
            <label htmlFor="motion-script" className="mb-2 flex items-center gap-2 text-sm font-bold text-white">
              <FileText className="h-4 w-4 text-sky-400" /> 2. Script {isAuto ? '(required)' : '(optional for Data / Shape / Outro)'}
            </label>
            <textarea
              id="motion-script"
              value={scriptText}
              onChange={(e) => setScriptText(e.target.value)}
              rows={5}
              className="w-full rounded-xl border border-slate-700 bg-slate-950/70 p-3 text-sm leading-relaxed text-slate-100 outline-none focus:border-sky-500"
              placeholder="Bilal qile mein aata hai. Zara mash'al jalati hai. Dono baat karte hain."
            />
            <p className="mt-1 text-[11px] text-slate-500">
              {isAuto
                ? 'Auto preserves parser scene order. Each parsed scene becomes one local HyperFrames clip; clip duration starts from the parser scene duration and is only clamped to the selected template range.'
                : 'Title uses the first parsed scene for setting/timing. Quote uses the first scene with dialogue (plus a second line as the response).'}
            </p>
          </div>

          {isAuto ? (
            <div className="rounded-xl border border-amber-500/25 bg-amber-500/5 p-4">
              <div className="flex items-center gap-2 text-sm font-bold text-white">
                <Braces className="h-4 w-4 text-amber-400" /> 3. Auto-generated requests
              </div>
              <p className="mt-2 text-xs leading-relaxed text-slate-400">
                No JSON overrides are needed in Auto mode. The planner generates each clip request
                from the script and validates the complete plan before a job can be queued. Use
                Preview / Validate to inspect scenes, templates, copy and durations.
              </p>
              <label
                htmlFor="include-dialogue-audio"
                className={`mt-3 flex cursor-pointer items-start gap-3 rounded-lg border border-slate-700 bg-slate-950/60 p-3 ${
                  mode !== 'render' ? 'cursor-not-allowed opacity-50' : ''
                }`}
              >
                <input
                  id="include-dialogue-audio"
                  type="checkbox"
                  checked={includeDialogueAudio}
                  disabled={mode !== 'render'}
                  onChange={(e) => setIncludeDialogueAudio(e.target.checked)}
                  className="mt-0.5 h-4 w-4 shrink-0 accent-emerald-400"
                />
                <span>
                  <span className="flex items-center gap-1.5 text-xs font-bold text-white">
                    <Volume2 className="h-4 w-4 text-emerald-300" /> Include Dialogue Audio
                  </span>
                  <span className="mt-1 block text-[11px] leading-relaxed text-slate-400">
                    Generate local Piper/eSpeak voices for parsed dialogue and mux them into the
                    final MP4. Render mode only; scenes without dialogue stay silent.
                  </span>
                </span>
              </label>
            </div>
          ) : (
            <div>
              <label htmlFor="motion-request" className="mb-2 flex items-center gap-2 text-sm font-bold text-white">
                <Braces className="h-4 w-4 text-purple-400" /> 3. Request overrides JSON
              </label>
              <textarea
                id="motion-request"
                value={requestText}
                onChange={(e) => setRequestText(e.target.value)}
                rows={7}
                spellCheck={false}
                className="w-full rounded-xl border border-slate-700 bg-slate-950/70 p-3 font-mono text-xs leading-relaxed text-slate-100 outline-none focus:border-purple-500"
                placeholder='{"duration_sec": 8}'
              />
              <p className="mt-1 text-[11px] text-slate-500">
                Leave <span className="font-mono text-slate-300">{'{}'}</span> to use script-derived values and template defaults. Invalid fields are rejected before a job is queued.
              </p>
            </div>
          )}

          <div className="grid gap-3 sm:grid-cols-3">
            <label className="space-y-1 text-xs font-semibold text-slate-300">
              Mode
              <select
                value={mode}
                onChange={(e) => setMode(e.target.value as MotionJobMode)}
                className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
              >
                <option value="render">{isAuto ? 'Build clips + render combined MP4' : 'Build + render MP4'}</option>
                <option value="build_only">{isAuto ? 'Build all clip projects only' : 'Build project only'}</option>
              </select>
            </label>
            <label className="space-y-1 text-xs font-semibold text-slate-300">
              FPS
              <select
                value={fps}
                onChange={(e) => setFps(Number(e.target.value) as 24 | 30 | 60)}
                className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
              >
                <option value={24}>24</option>
                <option value={30}>30</option>
                <option value={60}>60</option>
              </select>
            </label>
            <label className="space-y-1 text-xs font-semibold text-slate-300">
              Quality
              <select
                value={quality}
                onChange={(e) => setQuality(e.target.value as MotionJobQuality)}
                className="w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
              >
                <option value="draft">Draft</option>
                <option value="standard">Standard</option>
                <option value="high">High</option>
              </select>
            </label>
          </div>

          <div className="flex flex-wrap gap-2">
            <button
              onClick={handlePreview}
              disabled={busyPreview || busySubmit}
              className="inline-flex items-center gap-2 rounded-lg border border-sky-500/40 bg-sky-500/15 px-4 py-2.5 text-sm font-bold text-sky-200 hover:bg-sky-500/25 disabled:opacity-50"
            >
              <Eye className="h-4 w-4" /> {busyPreview ? 'Validating…' : 'Preview / Validate'}
            </button>
            <button
              onClick={handleQueue}
              disabled={busyPreview || busySubmit}
              className="inline-flex items-center gap-2 rounded-lg bg-amber-500 px-4 py-2.5 text-sm font-black text-slate-950 hover:bg-amber-400 disabled:opacity-50"
            >
              {mode === 'render' ? <Play className="h-4 w-4" /> : <Hammer className="h-4 w-4" />}
              {busySubmit
                ? 'Queueing…'
                : isAuto
                  ? mode === 'render'
                    ? 'Queue Auto Video'
                    : 'Queue Auto Build'
                  : mode === 'render'
                    ? 'Queue Render Job'
                    : 'Queue Build Job'}
            </button>
          </div>

          <div className="rounded-xl border border-slate-800 bg-slate-950/40 p-3 text-[11px] leading-relaxed text-slate-500">
            Rendering runs the locally configured HyperFrames {selectedTemplate?.hyperframes_version || '0.8.220'} CLI with inline
            strict variables, then verifies the MP4 from disk. In Auto mode, each clip is rendered and
            verified first, then the combined MP4 is verified again before the job completes.
            {isAuto && includeDialogueAudio && mode === 'render'
              ? ' Parsed dialogue is then synthesized locally, muxed as AAC, and the final voice MP4 is verified with its audio stream.'
              : ''}
          </div>
        </section>

        <section className="space-y-5">
          <div className="rounded-2xl border border-slate-800 bg-[#111520] p-5">
            <h3 className="text-sm font-bold text-white">
              {isAuto ? 'Parser & auto clip plan' : 'Parser & prepared request'}
            </h3>
            {!preview ? (
              <p className="mt-3 text-sm text-slate-500">
                {isAuto
                  ? 'Run Preview / Validate to see parsed scenes and the exact clip sequence that will be queued.'
                  : 'Run Preview / Validate to see parsed scenes and the exact request that will be queued.'}
              </p>
            ) : (
              <div className="mt-3 space-y-3">
                {preview.template === 'auto' ? (
                  <div className="grid grid-cols-2 gap-2 text-center sm:grid-cols-4">
                    <div className="rounded-lg bg-slate-900 p-3">
                      <div className="text-lg font-black text-white">{preview.scene_count}</div>
                      <div className="text-[10px] uppercase tracking-wider text-slate-500">Scenes</div>
                    </div>
                    <div className="rounded-lg bg-slate-900 p-3">
                      <div className="text-lg font-black text-white">{preview.clip_count}</div>
                      <div className="text-[10px] uppercase tracking-wider text-slate-500">Clips</div>
                    </div>
                    <div className="rounded-lg bg-slate-900 p-3">
                      <div className="text-lg font-black text-white">{preview.total_duration_sec}s</div>
                      <div className="text-[10px] uppercase tracking-wider text-slate-500">Duration</div>
                    </div>
                    <div className="rounded-lg bg-slate-900 p-3">
                      <div className="truncate text-lg font-black text-white">auto</div>
                      <div className="text-[10px] uppercase tracking-wider text-slate-500">Mode</div>
                    </div>
                  </div>
                ) : (
                  <div className="grid grid-cols-3 gap-2 text-center">
                    <div className="rounded-lg bg-slate-900 p-3">
                      <div className="text-lg font-black text-white">{preview.scene_count}</div>
                      <div className="text-[10px] uppercase tracking-wider text-slate-500">Scenes</div>
                    </div>
                    <div className="rounded-lg bg-slate-900 p-3">
                      <div className="truncate text-lg font-black text-white">{preview.template}</div>
                      <div className="text-[10px] uppercase tracking-wider text-slate-500">Template</div>
                    </div>
                    <div className="rounded-lg bg-slate-900 p-3">
                      <div className="text-lg font-black text-white">{String(preview.request.duration_sec ?? '—')}s</div>
                      <div className="text-[10px] uppercase tracking-wider text-slate-500">Duration</div>
                    </div>
                  </div>
                )}

                {preview.scenes.map((scene) => (
                  <div key={scene.scene_id} className="rounded-lg border border-slate-800 bg-slate-950/50 p-3 text-xs text-slate-300">
                    <div className="font-bold text-white">
                      Scene {scene.scene_id} · {scene.location} · {scene.time_of_day}
                    </div>
                    <div className="mt-1 text-slate-500">
                      Characters: {scene.characters.join(', ') || '—'} · Actions: {scene.actions.join(', ') || '—'}
                    </div>
                    {scene.dialogue.map((line, idx) => (
                      <div key={idx} className="mt-1 text-sky-200">
                        <strong>{line.speaker}:</strong> {line.line}
                      </div>
                    ))}
                  </div>
                ))}

                {preview.template === 'auto' && (
                  <div className="space-y-2">
                    <div className="text-xs font-bold uppercase tracking-wider text-slate-300">
                      Planned clips (parser order)
                    </div>
                    {preview.clips.map((clip) => (
                      <div key={clip.clip_id} className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-3 text-xs text-slate-300">
                        <div className="flex flex-wrap items-center justify-between gap-2">
                          <span className="font-bold text-white">
                            {clip.clip_id} · {clip.template}
                          </span>
                          <span className="rounded-full bg-slate-800 px-2 py-1 font-mono text-[10px] text-slate-300">
                            scene {clip.scene_duration_sec}s → clip {clip.duration_sec}s
                          </span>
                        </div>
                        <div className="mt-1 text-slate-400">{clip.sentence_text}</div>
                        <div className="mt-1 font-mono text-[10px] text-amber-200/80">
                          {clip.reason_codes.join(', ')}
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                <details className="rounded-lg border border-slate-800 bg-slate-950/50 p-3">
                  <summary className="cursor-pointer text-xs font-bold text-slate-200">
                    {preview.template === 'auto' ? 'Auto plan JSON' : 'Prepared request JSON'}
                  </summary>
                  <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap font-mono text-[11px] leading-relaxed text-slate-400">
                    {JSON.stringify(
                      preview.template === 'auto' ? preview.plan : preview.request,
                      null,
                      2
                    )}
                  </pre>
                </details>
              </div>
            )}
          </div>

          <div className="rounded-2xl border border-slate-800 bg-[#111520] p-5">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-bold text-white">Motion jobs</h3>
              <span className="rounded-full bg-slate-800 px-2 py-1 text-[11px] text-slate-400">{motionJobs.length}</span>
            </div>

            {motionJobs.length === 0 ? (
              <p className="mt-3 text-sm text-slate-500">No motion-graphics jobs yet.</p>
            ) : (
              <div className="mt-3 space-y-3">
                {motionJobs.map((job) => {
                  const expanded = expandedJobId === job.id;
                  const videoUrl = job.output_paths?.video
                    ? apiUrl(`/api/jobs/${job.id}/artifacts/video?v=${encodeURIComponent(job.updated_at || '')}`)
                    : '';
                  const preferredArtifactKeys = [
                    'auto_plan_json',
                    'sequence_result_json',
                    'index_html',
                    'variables_json',
                    'build_manifest',
                    'parsed_scenes',
                    'render_log',
                    'dialogue_audio_wav',
                    'dialogue_audio_json',
                    'verification_json',
                    'verification_with_audio_json',
                    'combined_video_silent',
                  ];
                  const dynamicArtifactKeys = Object.keys(job.output_paths || {})
                    .filter(
                      (key) =>
                        /^clip_\d+_/.test(key) &&
                        typeof job.output_paths?.[key] === 'string' &&
                        job.output_paths[key]
                    )
                    .sort();
                  const artifactKeys = [
                    ...preferredArtifactKeys.filter(
                      (key) => typeof job.output_paths?.[key] === 'string' && job.output_paths[key]
                    ),
                    ...dynamicArtifactKeys,
                  ];
                  const autoPlan = job.output_paths?.auto_plan as
                    | { clips?: Array<Record<string, any>>; total_duration_sec?: number }
                    | undefined;
                  const verification = job.output_paths?.verification as
                    | Record<string, any>
                    | undefined;
                  const dialogueAudio = job.output_paths?.dialogue_audio as
                    | {
                        line_count?: number;
                        engines?: string[];
                        lines?: Array<Record<string, any>>;
                      }
                    | undefined;
                  const verificationStreams = Array.isArray(verification?.streams)
                    ? (verification.streams as Array<Record<string, any>>)
                    : [];
                  const hasDialogueAudio =
                    Boolean(job.output_paths?.has_dialogue_audio) ||
                    verificationStreams.some((stream) => stream.type === 'audio');
                  return (
                    <article key={job.id} className="rounded-xl border border-slate-800 bg-slate-950/50 p-3">
                      <button
                        onClick={() => setExpandedJobId(expanded ? null : job.id)}
                        className="flex w-full items-center justify-between gap-2 text-left"
                      >
                        <span className="min-w-0">
                          <span className="block truncate font-mono text-[11px] text-amber-300">{job.id}</span>
                          <span className="block truncate text-sm font-bold text-white">
                            {String(job.payload?.template || 'motion')} · {String(job.payload?.mode || 'render')}
                            {job.payload?.include_dialogue_audio ? ' · dialogue audio' : ''}
                          </span>
                        </span>
                        <span className="flex shrink-0 items-center gap-2">
                          <span className={`rounded-full px-2 py-1 text-[10px] font-bold ${statusClasses(job.status)}`}>
                            {job.status}
                          </span>
                          {expanded ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                        </span>
                      </button>

                      <div className="mt-2 text-[11px] text-slate-500">{job.current_stage}</div>
                      {job.progress_measurable && job.progress_pct !== null && (
                        <div className="mt-2 h-2 overflow-hidden rounded-full bg-slate-800">
                          <div
                            className="h-full rounded-full bg-amber-500 transition-all"
                            style={{ width: `${Math.max(0, Math.min(100, job.progress_pct))}%` }}
                          />
                        </div>
                      )}

                      {expanded && (
                        <div className="mt-3 space-y-3">
                          {videoUrl && job.status === 'completed' && (
                            <>
                              <video src={videoUrl} controls className="aspect-video w-full rounded-lg bg-black" />
                              <div className="flex flex-wrap items-center gap-2">
                                <a
                                  href={apiUrl(`/api/jobs/${job.id}/artifacts/video`)}
                                  download={`${job.id}-motion-video.mp4`}
                                  className="inline-flex items-center gap-1.5 rounded-md bg-emerald-500 px-3 py-2 text-[11px] font-black text-slate-950 hover:bg-emerald-400"
                                >
                                  <Download className="h-3.5 w-3.5" /> Download MP4
                                </a>
                                {verification && (
                                  <span className="rounded-md bg-slate-800 px-2 py-1.5 font-mono text-[10px] text-slate-300">
                                    {String(verification.width ?? '—')}×{String(verification.height ?? '—')} ·{' '}
                                    {String(verification.fps ?? '—')}fps · {String(verification.duration_sec ?? '—')}s
                                  </span>
                                )}
                                {hasDialogueAudio && (
                                  <span className="inline-flex items-center gap-1 rounded-md bg-emerald-500/15 px-2 py-1.5 font-mono text-[10px] text-emerald-200">
                                    <Volume2 className="h-3 w-3" /> Dialogue audio · AAC
                                    {dialogueAudio?.line_count
                                      ? ` · ${dialogueAudio.line_count} lines`
                                      : ''}
                                  </span>
                                )}
                              </div>
                            </>
                          )}

                          {autoPlan?.clips && autoPlan.clips.length > 0 && (
                            <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-3">
                              <div className="text-[11px] font-bold uppercase tracking-wider text-amber-200">
                                Auto sequence · {autoPlan.clips.length} clips · {String(autoPlan.total_duration_sec ?? '—')}s
                              </div>
                              <div className="mt-2 flex flex-wrap gap-1.5">
                                {autoPlan.clips.map((clip) => (
                                  <span
                                    key={String(clip.clip_id)}
                                    className="rounded-full bg-slate-800 px-2 py-1 font-mono text-[10px] text-slate-300"
                                  >
                                    {String(clip.clip_id)} · {String(clip.template)} · {String(clip.duration_sec)}s
                                  </span>
                                ))}
                              </div>
                            </div>
                          )}

                          {dialogueAudio?.lines && dialogueAudio.lines.length > 0 && (
                            <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-3">
                              <div className="flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-emerald-200">
                                <Volume2 className="h-3.5 w-3.5" /> Local dialogue audio
                                {dialogueAudio.engines?.length
                                  ? ` · ${dialogueAudio.engines.join(', ')}`
                                  : ''}
                              </div>
                              <div className="mt-2 space-y-1.5">
                                {dialogueAudio.lines.map((line, index) => (
                                  <div
                                    key={`${String(line.clip_id)}-${index}`}
                                    className="rounded-md bg-slate-900/80 px-2 py-1.5 text-[11px] text-slate-300"
                                  >
                                    <strong className="text-white">{String(line.speaker)}:</strong>{' '}
                                    {String(line.text)}{' '}
                                    <span className="font-mono text-[10px] text-slate-500">
                                      @{String(line.start_sec)}s · {String(line.voice_id)}
                                    </span>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          {job.output_paths?.project_dir && (
                            <div className="break-all rounded-lg border border-slate-800 bg-black/30 px-3 py-2 font-mono text-[10px] text-slate-400">
                              Project: {job.output_paths.project_dir}
                            </div>
                          )}

                          <div className="flex flex-wrap gap-1.5">
                            {(job.status === 'queued' || job.status === 'running' || job.status === 'paused') && (
                              <button
                                onClick={() => controlJob(job.id, 'cancel')}
                                className="inline-flex items-center gap-1 rounded-md bg-red-500/15 px-2 py-1.5 text-[11px] font-bold text-red-300"
                              >
                                <XCircle className="h-3.5 w-3.5" /> Cancel
                              </button>
                            )}
                            {job.status === 'running' && (
                              <button
                                onClick={() => controlJob(job.id, 'pause')}
                                className="rounded-md bg-slate-800 px-2 py-1.5 text-[11px] font-bold text-slate-200"
                              >
                                Pause
                              </button>
                            )}
                            {job.status === 'paused' && (
                              <button
                                onClick={() => controlJob(job.id, 'resume')}
                                className="rounded-md bg-slate-800 px-2 py-1.5 text-[11px] font-bold text-slate-200"
                              >
                                Resume
                              </button>
                            )}
                            {(job.status === 'failed' || job.status === 'cancelled' || job.status === 'interrupted') && (
                              <button
                                onClick={() => controlJob(job.id, 'retry')}
                                className="inline-flex items-center gap-1 rounded-md bg-amber-500/15 px-2 py-1.5 text-[11px] font-bold text-amber-300"
                              >
                                <RotateCcw className="h-3.5 w-3.5" /> Retry
                              </button>
                            )}
                            <button
                              onClick={() => api.get(`/api/jobs/${job.id}`).then(onJobUpdated)}
                              className="inline-flex items-center gap-1 rounded-md bg-slate-800 px-2 py-1.5 text-[11px] font-bold text-slate-200"
                            >
                              <RefreshCw className="h-3.5 w-3.5" /> Refresh
                            </button>
                          </div>

                          {artifactKeys.length > 0 && (
                            <div className="flex flex-wrap gap-1.5">
                              {artifactKeys.map((key) => (
                                <a
                                  key={key}
                                  href={apiUrl(`/api/jobs/${job.id}/artifacts/${key}`)}
                                  target="_blank"
                                  rel="noreferrer"
                                  className="inline-flex items-center gap-1 rounded-md border border-slate-700 px-2 py-1 text-[10px] text-slate-300 hover:bg-slate-800"
                                >
                                  <Download className="h-3 w-3" /> {key}
                                </a>
                              ))}
                            </div>
                          )}

                          {job.error_details && (
                            <div className="rounded-lg bg-red-500/10 p-2 text-[11px] text-red-200">{job.error_details}</div>
                          )}

                          <details>
                            <summary className="cursor-pointer text-[11px] font-bold text-slate-300">
                              <Film className="mr-1 inline h-3.5 w-3.5" /> Job logs
                            </summary>
                            <pre className="mt-2 max-h-56 overflow-auto whitespace-pre-wrap rounded-lg bg-black/50 p-2 font-mono text-[10px] leading-relaxed text-slate-400">
                              {(job.logs || []).slice(-40).join('\n')}
                            </pre>
                          </details>
                        </div>
                      )}
                    </article>
                  );
                })}
              </div>
            )}
          </div>
        </section>
      </div>
    </div>
  );
};
