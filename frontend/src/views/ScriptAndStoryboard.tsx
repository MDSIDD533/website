import React, { useEffect, useState } from 'react';
import {
  Sparkles,
  Save,
  Play,
  RefreshCw,
  Camera,
  Sun,
  CloudRain,
  Swords,
  MessageSquare,
  CheckCircle2,
  AlertCircle,
  Film,
} from 'lucide-react';
import { api, apiUrl, basenameFromPath } from '../api';
import { NavSection, ProjectSummary, SceneItem } from '../types';

interface ScriptEditorProps {
  project: ProjectSummary | null;
  onProjectUpdated: (p: ProjectSummary) => void;
  onNavigate: (nav: NavSection) => void;
}

export const ScriptEditorView: React.FC<ScriptEditorProps> = ({
  project,
  onProjectUpdated,
  onNavigate,
}) => {
  const [scriptText, setScriptText] = useState(project?.script_text || '');
  const [language, setLanguage] = useState(project?.language || 'en');
  const [analysisPreview, setAnalysisPreview] = useState<any>(project?.analysis || null);
  const [saving, setSaving] = useState(false);
  const [rebuilding, setRebuilding] = useState(false);
  const [msg, setMsg] = useState('');

  useEffect(() => {
    setScriptText(project?.script_text || '');
    setLanguage(project?.language || 'en');
    setAnalysisPreview(project?.analysis || null);
  }, [project?.id]);

  if (!project) {
    return (
      <div className="rounded-xl border border-slate-800 bg-[#111520] p-8 text-center">
        <p className="text-sm text-slate-400">Select or create a project first to edit its script.</p>
        <button
          onClick={() => onNavigate('create')}
          className="mt-3 rounded-lg bg-amber-500 px-4 py-2 text-xs font-semibold text-slate-950"
        >
          Create Project
        </button>
      </div>
    );
  }

  const handleSaveDraft = async () => {
    setSaving(true);
    setMsg('');
    try {
      const updated = await api.patch<ProjectSummary>(`/api/projects/${project.id}`, {
        script_text: scriptText,
        language,
      });
      onProjectUpdated(updated);
      setMsg('Script saved locally.');
    } catch (e: any) {
      setMsg(`Error: ${e.message}`);
    } finally {
      setSaving(false);
    }
  };

  const handleAnalyzePreview = async () => {
    setMsg('');
    try {
      const res = await api.post('/api/projects/analyze-preview', {
        script_text: scriptText,
        language,
        target_scenes: project.num_scenes_target,
        genre: project.genre,
        historical_accuracy_mode: project.historical_accuracy_mode,
      });
      setAnalysisPreview(res);
    } catch (e: any) {
      setMsg(`Analysis error: ${e.message}`);
    }
  };

  const handleRebuildStoryboard = async () => {
    setRebuilding(true);
    setMsg('');
    try {
      const updated = await api.post<ProjectSummary>(`/api/projects/${project.id}/storyboard`, {
        script_text: scriptText,
      });
      onProjectUpdated(updated);
      onNavigate('storyboard');
    } catch (e: any) {
      setMsg(`Storyboard error: ${e.message}`);
    } finally {
      setRebuilding(false);
    }
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold text-white">Script Editor — {project.title}</h2>
          <p className="text-xs text-slate-400">
            Supports English, Roman Urdu, and Urdu (اردو). Story text is processed strictly as inert structured data.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={language}
            onChange={(e) => setLanguage(e.target.value)}
            className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs text-white"
          >
            <option value="en">English</option>
            <option value="roman_ur">Roman Urdu</option>
            <option value="ur">Urdu (اردو)</option>
          </select>
          <button
            onClick={handleAnalyzePreview}
            className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-xs font-medium text-slate-200 hover:bg-slate-700"
          >
            Preview Analysis
          </button>
          <button
            onClick={handleSaveDraft}
            disabled={saving}
            className="inline-flex items-center gap-1.5 rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-xs font-medium text-slate-200 hover:bg-slate-700"
          >
            <Save className="h-3.5 w-3.5" /> {saving ? 'Saving...' : 'Save Script'}
          </button>
          <button
            onClick={handleRebuildStoryboard}
            disabled={rebuilding}
            className="inline-flex items-center gap-1.5 rounded-lg bg-amber-500 px-4 py-2 text-xs font-bold text-slate-950 hover:bg-amber-400"
          >
            <Sparkles className="h-3.5 w-3.5" />
            {rebuilding ? 'Generating...' : 'Generate / Update Storyboard'}
          </button>
        </div>
      </div>

      {msg && <div className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs text-amber-300">{msg}</div>}

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <div className="lg:col-span-2 rounded-xl border border-slate-800 bg-[#111520] p-4">
          <textarea
            value={scriptText}
            onChange={(e) => setScriptText(e.target.value)}
            dir={language === 'ur' ? 'rtl' : 'ltr'}
            rows={20}
            className="w-full rounded-lg border border-slate-800 bg-[#090c14] p-4 font-mono text-sm leading-relaxed text-slate-100 focus:border-amber-500 focus:outline-none"
          />
        </div>

        <div className="space-y-4 rounded-xl border border-slate-800 bg-[#111520] p-4">
          <h3 className="text-sm font-semibold text-white">Structured Story Extraction</h3>
          {analysisPreview && analysisPreview.characters ? (
            <div className="space-y-3 text-xs">
              <div className="grid grid-cols-2 gap-2">
                <div className="rounded-lg bg-slate-900 p-2.5">
                  <div className="text-slate-400">Detected Language</div>
                  <div className="mt-0.5 font-semibold uppercase text-amber-300">
                    {analysisPreview.effective_language}
                  </div>
                </div>
                <div className="rounded-lg bg-slate-900 p-2.5">
                  <div className="text-slate-400">Dialogue Lines</div>
                  <div className="mt-0.5 font-semibold text-white">{analysisPreview.dialogue_count || 0}</div>
                </div>
              </div>

              <div>
                <div className="font-medium text-slate-300 mb-1">Extracted Characters</div>
                <div className="flex flex-wrap gap-1.5">
                  {(analysisPreview.characters || []).map((c: any) => (
                    <span
                      key={c.name}
                      className="rounded-md border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-amber-200"
                    >
                      {c.name} ({c.default_voice_id})
                    </span>
                  ))}
                </div>
              </div>

              <div>
                <div className="font-medium text-slate-300 mb-1">Locations &amp; Props</div>
                <div className="text-slate-400">
                  Locations: {(analysisPreview.locations || []).join(' • ') || 'Auto'}
                </div>
                <div className="mt-1 text-slate-400">
                  Props: {(analysisPreview.props || []).join(', ') || 'None specified'}
                </div>
              </div>

              <div>
                <div className="font-medium text-slate-300 mb-1">Actions &amp; Emotions</div>
                <div className="text-slate-400">
                  Actions: {(analysisPreview.actions || []).join(', ')}
                </div>
                <div className="mt-1 text-slate-400">
                  Emotions: {(analysisPreview.emotions || []).join(', ')}
                </div>
              </div>

              <div>
                <div className="font-medium text-slate-300 mb-1">Key Story Beats</div>
                <ul className="space-y-1 text-slate-400">
                  {(analysisPreview.story_events || []).map((ev: string, i: number) => (
                    <li key={i} className="truncate">• {ev}</li>
                  ))}
                </ul>
              </div>
            </div>
          ) : (
            <p className="text-xs text-slate-400">
              Click &ldquo;Preview Analysis&rdquo; or &ldquo;Generate Storyboard&rdquo; to inspect extracted characters, locations, dialogue, and props.
            </p>
          )}
        </div>
      </div>
    </div>
  );
};

interface StoryboardViewProps {
  project: ProjectSummary | null;
  environments: any[];
  cameraShots: any[];
  cameraMovements: string[];
  voices: any[];
  onSceneUpdated: (scene: SceneItem) => void;
  onRenderScene: (sceneId: string) => Promise<void>;
  onRenderFullProject: (forceRerender?: boolean) => Promise<void>;
  onNavigate: (nav: NavSection) => void;
}

export const StoryboardView: React.FC<StoryboardViewProps> = ({
  project,
  environments,
  cameraShots,
  cameraMovements,
  voices,
  onSceneUpdated,
  onRenderScene,
  onRenderFullProject,
  onNavigate,
}) => {
  const [editingSceneId, setEditingSceneId] = useState<string | null>(null);
  const [previewVideoUrl, setPreviewVideoUrl] = useState<string | null>(null);

  if (!project) {
    return (
      <div className="rounded-xl border border-slate-800 bg-[#111520] p-8 text-center">
        <p className="text-sm text-slate-400">No active project selected.</p>
        <button
          onClick={() => onNavigate('create')}
          className="mt-3 rounded-lg bg-amber-500 px-4 py-2 text-xs font-semibold text-slate-950"
        >
          Create Project
        </button>
      </div>
    );
  }

  const scenes = project.scenes || [];

  const patchSceneField = async (scene: SceneItem, patch: Record<string, any>) => {
    const updated = await api.patch<SceneItem>(
      `/api/projects/${project.id}/scenes/${scene.id}`,
      patch
    );
    onSceneUpdated(updated);
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold text-white">Storyboard — {project.title}</h2>
          <p className="text-xs text-slate-400">
            Review and customize every scene&apos;s 3D environment, camera, weather, dialogue, and choreography before rendering.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            onClick={() => onNavigate('timeline')}
            className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-2 text-xs font-medium text-slate-200 hover:bg-slate-700"
          >
            Open Scene Timeline
          </button>
          <button
            onClick={() => onRenderFullProject(false)}
            className="inline-flex items-center gap-2 rounded-lg bg-amber-500 px-4 py-2 text-xs font-bold text-slate-950 shadow hover:bg-amber-400"
          >
            <Film className="h-4 w-4" /> Render Full MP4 Video
          </button>
        </div>
      </div>

      {previewVideoUrl && (
        <div className="rounded-xl border border-amber-500/40 bg-[#111520] p-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold text-amber-300">Rendered Scene Preview</span>
            <button onClick={() => setPreviewVideoUrl(null)} className="text-xs text-slate-400 hover:text-white">
              Close Preview
            </button>
          </div>
          <video src={previewVideoUrl} controls autoPlay className="mx-auto max-h-80 rounded-lg bg-black" />
        </div>
      )}

      {scenes.length === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-700 bg-[#111520] p-8 text-center">
          <p className="text-sm text-slate-400">This project has no storyboard scenes yet.</p>
          <button
            onClick={() => onNavigate('script')}
            className="mt-3 rounded-lg bg-amber-500 px-4 py-2 text-xs font-semibold text-slate-950"
          >
            Go to Script Editor &amp; Generate Storyboard
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-5 xl:grid-cols-2">
          {scenes.map((sc) => {
            const thumbName = basenameFromPath(sc.thumbnail_path);
            const thumbUrl = thumbName
              ? apiUrl(`/api/media/project/${project.id}/thumbnails/${thumbName}?t=${encodeURIComponent(sc.updated_at || '')}`)
              : '';
            const clipName = basenameFromPath(sc.rendered_video_path);
            const clipUrl = clipName ? apiUrl(`/api/media/project/${project.id}/renders/${clipName}`) : '';
            const isEditing = editingSceneId === sc.id;

            return (
              <div key={sc.id} className="rounded-xl border border-slate-800 bg-[#121723] p-4 flex flex-col gap-3">
                <div className="flex items-start justify-between gap-2">
                  <div>
                    <span className="text-[11px] font-semibold uppercase tracking-wider text-amber-400">
                      Scene {sc.scene_index + 1} • {sc.duration_sec}s • {sc.transition_type}
                    </span>
                    <h3 className="text-base font-semibold text-white">{sc.title}</h3>
                  </div>
                  <span
                    className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[11px] font-medium ${
                      sc.generation_status === 'completed'
                        ? 'bg-emerald-500/15 text-emerald-300'
                        : sc.generation_status === 'failed'
                        ? 'bg-red-500/15 text-red-300'
                        : sc.generation_status === 'rendering'
                        ? 'bg-sky-500/15 text-sky-300'
                        : 'bg-slate-800 text-slate-300'
                    }`}
                  >
                    {sc.generation_status === 'completed' && <CheckCircle2 className="h-3 w-3" />}
                    {sc.generation_status === 'failed' && <AlertCircle className="h-3 w-3" />}
                    {sc.generation_status}
                  </span>
                </div>

                {/* Thumbnail or Blueprint */}
                <div className="relative aspect-video overflow-hidden rounded-lg border border-slate-800 bg-[#0b0e16] flex items-center justify-center">
                  {thumbUrl ? (
                    <img src={thumbUrl} alt={sc.title} className="h-full w-full object-cover" />
                  ) : (
                    <div className="p-4 text-center text-xs text-slate-500">
                      <Camera className="mx-auto mb-1.5 h-6 w-6 text-slate-600" />
                      3D Scene Ready: <strong className="text-slate-300">{sc.environment_preset}</strong> ({sc.time_of_day}, {sc.weather})
                      <div className="mt-1 text-[11px]">Click &ldquo;Render Scene&rdquo; to raytrace 3D preview &amp; clip</div>
                    </div>
                  )}
                  {sc.combat_choreography?.enabled && (
                    <span className="absolute left-2 top-2 inline-flex items-center gap-1 rounded bg-red-600/85 px-2 py-0.5 text-[10px] font-bold uppercase text-white">
                      <Swords className="h-3 w-3" /> Combat Choreography
                    </span>
                  )}
                </div>

                {/* Quick Pill Metadata */}
                <div className="flex flex-wrap gap-1.5 text-[11px] text-slate-300">
                  <span className="rounded bg-slate-800/90 px-2 py-0.5 inline-flex items-center gap-1">
                    <Sun className="h-3 w-3 text-amber-400" /> {sc.environment_preset} • {sc.time_of_day}
                  </span>
                  <span className="rounded bg-slate-800/90 px-2 py-0.5 inline-flex items-center gap-1">
                    <CloudRain className="h-3 w-3 text-sky-400" /> {sc.weather}
                  </span>
                  <span className="rounded bg-slate-800/90 px-2 py-0.5 inline-flex items-center gap-1">
                    <Camera className="h-3 w-3 text-purple-400" /> {sc.camera_shot} ({sc.camera_movement})
                  </span>
                </div>

                {/* Dialogue & Narration Summary */}
                <div className="rounded-lg bg-[#0d111b] p-3 text-xs space-y-1.5 border border-slate-800/80">
                  {sc.dialogue.length > 0 ? (
                    sc.dialogue.map((d, idx) => (
                      <div key={idx} className="flex items-start gap-1.5">
                        <MessageSquare className="h-3.5 w-3.5 text-amber-400 shrink-0 mt-0.5" />
                        <div>
                          <span className="font-semibold text-amber-300">{d.speaker}</span>{' '}
                          <span className="text-slate-500">({d.emotion})</span>:{' '}
                          <span className="text-slate-200">{d.text}</span>
                        </div>
                      </div>
                    ))
                  ) : (
                    <div className="text-slate-300">
                      <span className="font-semibold text-sky-300">Narration: </span>
                      {sc.narration_text || 'Visual action scene'}
                    </div>
                  )}
                </div>

                {/* Historical Accuracy Distinction Badge when enabled */}
                {sc.historical_notes?.mode_enabled && (
                  <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-2.5 text-[11px] text-slate-300">
                    <div className="font-semibold text-amber-300">Historical vs. Fictional Distinction:</div>
                    <div className="text-slate-400">
                      • Verified Period Archetype: {sc.historical_notes.verified_period_elements?.[0]}
                    </div>
                    <div className="text-slate-400">
                      • Dramatized Story Element: {sc.historical_notes.dramatized_fictional_elements?.[0]}
                    </div>
                  </div>
                )}

                {sc.error_message && (
                  <div className="rounded bg-red-500/10 border border-red-500/30 p-2 text-xs text-red-300">
                    Error: {sc.error_message}
                  </div>
                )}

                {/* Inline Scene Editor */}
                {isEditing && (
                  <div className="space-y-3 rounded-lg border border-slate-700 bg-slate-900/90 p-3 text-xs">
                    <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                      <div>
                        <label className="block text-slate-400 mb-1">Environment</label>
                        <select
                          value={sc.environment_preset}
                          onChange={(e) => patchSceneField(sc, { environment_preset: e.target.value })}
                          className="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1 text-white"
                        >
                          {environments.map((env) => (
                            <option key={env.id} value={env.id}>{env.label}</option>
                          ))}
                        </select>
                      </div>
                      <div>
                        <label className="block text-slate-400 mb-1">Time of Day</label>
                        <select
                          value={sc.time_of_day}
                          onChange={(e) => patchSceneField(sc, { time_of_day: e.target.value })}
                          className="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1 text-white"
                        >
                          {['sunrise', 'day', 'sunset', 'night'].map((t) => (
                            <option key={t} value={t}>{t}</option>
                          ))}
                        </select>
                      </div>
                      <div>
                        <label className="block text-slate-400 mb-1">Weather</label>
                        <select
                          value={sc.weather}
                          onChange={(e) => patchSceneField(sc, { weather: e.target.value })}
                          className="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1 text-white"
                        >
                          {['clear', 'rain', 'fog', 'smoke', 'fire', 'dust'].map((w) => (
                            <option key={w} value={w}>{w}</option>
                          ))}
                        </select>
                      </div>
                      <div>
                        <label className="block text-slate-400 mb-1">Camera Shot</label>
                        <select
                          value={sc.camera_shot}
                          onChange={(e) => patchSceneField(sc, { camera_shot: e.target.value })}
                          className="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1 text-white"
                        >
                          {cameraShots.map((cs) => (
                            <option key={cs.id} value={cs.id}>{cs.label}</option>
                          ))}
                        </select>
                      </div>
                      <div>
                        <label className="block text-slate-400 mb-1">Camera Movement</label>
                        <select
                          value={sc.camera_movement}
                          onChange={(e) => patchSceneField(sc, { camera_movement: e.target.value })}
                          className="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1 text-white"
                        >
                          {cameraMovements.map((cm) => (
                            <option key={cm} value={cm}>{cm}</option>
                          ))}
                        </select>
                      </div>
                      <div>
                        <label className="block text-slate-400 mb-1">Duration (sec)</label>
                        <input
                          type="number"
                          step="0.5"
                          min="1.5"
                          max="30"
                          value={sc.duration_sec}
                          onChange={(e) => patchSceneField(sc, { duration_sec: Number(e.target.value) })}
                          className="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1 text-white"
                        />
                      </div>
                    </div>

                    {sc.dialogue.length > 0 && (
                      <div className="space-y-2 pt-1">
                        <div className="font-medium text-slate-300">Edit Dialogue &amp; Speaker Voices</div>
                        {sc.dialogue.map((dlg, idx) => (
                          <div key={idx} className="grid grid-cols-1 sm:grid-cols-3 gap-2">
                            <select
                              value={dlg.voice_id}
                              onChange={(e) => {
                                const next = [...sc.dialogue];
                                next[idx] = { ...next[idx], voice_id: e.target.value };
                                patchSceneField(sc, { dialogue: next });
                              }}
                              className="rounded border border-slate-700 bg-slate-950 px-2 py-1 text-white"
                            >
                              {voices.map((v) => (
                                <option key={v.id} value={v.id}>{dlg.speaker}: {v.name}</option>
                              ))}
                            </select>
                            <input
                              value={dlg.text}
                              onChange={(e) => {
                                const next = [...sc.dialogue];
                                next[idx] = { ...next[idx], text: e.target.value };
                                patchSceneField(sc, { dialogue: next });
                              }}
                              className="sm:col-span-2 rounded border border-slate-700 bg-slate-950 px-2 py-1 text-white"
                            />
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                <div className="mt-auto flex flex-wrap gap-2 pt-1">
                  <button
                    onClick={() => setEditingSceneId(isEditing ? null : sc.id)}
                    className="rounded-lg border border-slate-700 bg-slate-800 px-3 py-1.5 text-xs font-medium text-slate-200 hover:bg-slate-700"
                  >
                    {isEditing ? 'Done Editing' : 'Edit Scene'}
                  </button>
                  <button
                    onClick={() => onRenderScene(sc.id)}
                    className="inline-flex items-center gap-1.5 rounded-lg bg-amber-500/20 border border-amber-500/40 px-3 py-1.5 text-xs font-semibold text-amber-300 hover:bg-amber-500/30"
                  >
                    <RefreshCw className="h-3.5 w-3.5" />
                    {sc.generation_status === 'completed' ? 'Regenerate 3D Scene' : 'Render 3D Scene'}
                  </button>
                  {clipUrl && sc.generation_status === 'completed' && (
                    <button
                      onClick={() => setPreviewVideoUrl(`${clipUrl}?t=${encodeURIComponent(sc.updated_at || '')}`)}
                      className="inline-flex items-center gap-1 rounded-lg bg-emerald-500/20 border border-emerald-500/40 px-3 py-1.5 text-xs font-semibold text-emerald-300 hover:bg-emerald-500/30"
                    >
                      <Play className="h-3.5 w-3.5" /> Play Clip
                    </button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
