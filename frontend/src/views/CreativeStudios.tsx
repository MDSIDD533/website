import React, { useEffect, useState } from 'react';
import {
  UserCheck,
  Sparkles,
  Plus,
  Volume2,
  Camera,
  Swords,
  ShieldCheck,
  Mountain,
  Check,
} from 'lucide-react';
import { api, basenameFromPath } from '../api';
import { CharacterProfile, ProjectSummary, SceneItem } from '../types';

/* ==================== CHARACTER STUDIO ==================== */
export const CharacterStudioView: React.FC<{
  project: ProjectSummary | null;
  voices: any[];
  onRefreshProject: () => Promise<void>;
  onNotify: (msg: string) => void;
}> = ({ project, voices, onRefreshProject, onNotify }) => {
  const [characters, setCharacters] = useState<CharacterProfile[]>([]);
  const [outfits, setOutfits] = useState<any[]>([]);
  const [newName, setNewName] = useState('');
  const [newOutfit, setNewOutfit] = useState('historical_armor');
  const [newVoice, setNewVoice] = useState('en_male_heroic');

  const loadChars = async () => {
    const q = project ? `?project_id=${project.id}` : '';
    const [charData, presetData] = await Promise.all([
      api.get(`/api/characters${q}`),
      api.get('/api/characters/presets'),
    ]);
    setCharacters(charData.characters || []);
    setOutfits(presetData.outfits || []);
  };

  useEffect(() => {
    loadChars();
  }, [project?.id, project?.updated_at]);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newName.trim()) return;
    await api.post('/api/characters', {
      project_id: project?.id || null,
      name: newName.trim(),
      outfit_preset: newOutfit,
      active_outfit: newOutfit,
      default_voice_id: newVoice,
      language: project?.language || 'en',
    });
    setNewName('');
    await loadChars();
    await onRefreshProject();
    onNotify('Persistent character profile created.');
  };

  const handlePatch = async (id: string, patch: Record<string, any>) => {
    await api.patch(`/api/characters/${id}`, patch);
    await loadChars();
    await onRefreshProject();
  };

  const handlePreviewRender = async (id: string) => {
    await api.post(`/api/characters/${id}/preview-render`);
    onNotify('Queued Blender 3D portrait render in Render Queue.');
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold text-white">Character Consistency Studio</h2>
          <p className="text-xs text-slate-400">
            Reusable articulated 3D character rigs (`sidd_humanoid_rig_v1`). Switch outfits freely without changing facial proportions or identity seed.
          </p>
        </div>
      </div>

      {/* Add Character Bar */}
      <form
        onSubmit={handleCreate}
        className="grid grid-cols-1 gap-3 sm:grid-cols-4 rounded-xl border border-slate-800 bg-[#111520] p-4"
      >
        <input
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          placeholder="New character name (e.g. Commander Tariq)"
          className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs text-white"
        />
        <select
          value={newOutfit}
          onChange={(e) => setNewOutfit(e.target.value)}
          className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs text-white"
        >
          {outfits.map((o) => (
            <option key={o.id} value={o.id}>{o.label}</option>
          ))}
        </select>
        <select
          value={newVoice}
          onChange={(e) => setNewVoice(e.target.value)}
          className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs text-white"
        >
          {voices.map((v) => (
            <option key={v.id} value={v.id}>{v.name}</option>
          ))}
        </select>
        <button
          type="submit"
          className="inline-flex items-center justify-center gap-1.5 rounded-lg bg-amber-500 px-4 py-2 text-xs font-bold text-slate-950 hover:bg-amber-400"
        >
          <Plus className="h-4 w-4" /> Add Character Profile
        </button>
      </form>

      {/* Character Cards */}
      <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3">
        {characters.map((ch) => {
          const previewFile = basenameFromPath(ch.preview_image_path);
          const previewUrl = previewFile
            ? `/api/media/preview/characters/${previewFile}?v=${encodeURIComponent(ch.name + ch.active_outfit)}`
            : '';

          return (
            <div key={ch.id} className="rounded-xl border border-slate-800 bg-[#121723] p-4 flex flex-col gap-3">
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="text-base font-bold text-white">{ch.name}</h3>
                  <div className="text-[11px] text-slate-400">
                    ID: {ch.id} • Identity Seed #{ch.identity_seed}
                  </div>
                </div>
                <button
                  onClick={() => handlePatch(ch.id, { approved: !ch.approved })}
                  className={`inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-[11px] font-semibold transition ${
                    ch.approved
                      ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                      : 'bg-slate-800 text-slate-300 border border-slate-700 hover:bg-slate-700'
                  }`}
                >
                  <UserCheck className="h-3.5 w-3.5" />
                  {ch.approved ? 'Approved' : 'Approve'}
                </button>
              </div>

              <div className="aspect-square max-h-56 overflow-hidden rounded-lg border border-slate-800 bg-[#0b0e16] flex items-center justify-center">
                {previewUrl ? (
                  <img src={previewUrl} alt={ch.name} className="h-full w-full object-cover" />
                ) : (
                  <div className="p-4 text-center text-xs text-slate-500">
                    3D Articulated Rig Ready
                    <div className="mt-1 text-[11px]">Click &ldquo;Render 3D Portrait&rdquo; to preview in Blender Cycles</div>
                  </div>
                )}
              </div>

              <div className="grid grid-cols-2 gap-2 text-xs">
                <div>
                  <label className="block text-[11px] text-slate-400 mb-1">Active Outfit (Identity Locked)</label>
                  <select
                    value={ch.active_outfit}
                    onChange={(e) => handlePatch(ch.id, { active_outfit: e.target.value })}
                    className="w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-white"
                  >
                    {outfits.map((o) => (
                      <option key={o.id} value={o.id}>{o.label}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <label className="block text-[11px] text-slate-400 mb-1">Default Voice</label>
                  <select
                    value={ch.default_voice_id}
                    onChange={(e) => handlePatch(ch.id, { default_voice_id: e.target.value })}
                    className="w-full rounded border border-slate-700 bg-slate-900 px-2 py-1.5 text-white"
                  >
                    {voices.map((v) => (
                      <option key={v.id} value={v.id}>{v.name}</option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="flex items-center justify-between text-xs">
                <div className="flex items-center gap-2">
                  <span className="text-slate-400">Skin &amp; Hair:</span>
                  <input
                    type="color"
                    value={ch.skin_tone}
                    onChange={(e) => handlePatch(ch.id, { skin_tone: e.target.value })}
                    title="Skin tone"
                    className="h-6 w-7 cursor-pointer rounded bg-transparent"
                  />
                  <input
                    type="color"
                    value={ch.hair_color}
                    onChange={(e) => handlePatch(ch.id, { hair_color: e.target.value })}
                    title="Hair color"
                    className="h-6 w-7 cursor-pointer rounded bg-transparent"
                  />
                </div>
                <div className="flex gap-1">
                  {ch.color_palette.map((hex, i) => (
                    <span
                      key={i}
                      style={{ backgroundColor: hex }}
                      className="h-4 w-4 rounded-full border border-white/20"
                    />
                  ))}
                </div>
              </div>

              <div className="rounded bg-[#0d111b] p-2 text-[11px] text-slate-400">
                <div><strong>Rig:</strong> {ch.rig_type} (Walk, Run, Idle, Jaw Lip-Sync, Sword/Hand Combat)</div>
                <div className="truncate"><strong>Note:</strong> {ch.consistency_method}</div>
              </div>

              <button
                onClick={() => handlePreviewRender(ch.id)}
                className="mt-auto inline-flex items-center justify-center gap-1.5 rounded-lg border border-amber-500/40 bg-amber-500/15 py-2 text-xs font-semibold text-amber-300 hover:bg-amber-500/25"
              >
                <Camera className="h-3.5 w-3.5" /> Render 3D Portrait Preview
              </button>
            </div>
          );
        })}
      </div>
    </div>
  );
};

/* ==================== VOICE STUDIO ==================== */
export const VoiceStudioView: React.FC<{
  voices: any[];
  capabilities: any[];
}> = ({ voices, capabilities }) => {
  const [selectedVoice, setSelectedVoice] = useState(voices[0]?.id || 'en_male_heroic');
  const [sampleText, setSampleText] = useState(
    'Sardar Tariq ne qilay ki deewar se registan ki taraf dekha. Hum taiyar hain!'
  );
  const [speed, setSpeed] = useState(1.0);
  const [pitch, setPitch] = useState(1.0);
  const [emotion, setEmotion] = useState('determined');
  const [previewResult, setPreviewResult] = useState<any>(null);
  const [loading, setLoading] = useState(false);

  const handleSynthesize = async () => {
    setLoading(true);
    try {
      const res = await api.post('/api/voices/preview', {
        text: sampleText,
        voice_id: selectedVoice,
        speed,
        pitch,
        emotion,
      });
      setPreviewResult(res);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold text-white">Local Voice, Roman-Urdu &amp; Lip-Sync Studio</h2>
        <p className="text-xs text-slate-400">
          100% local speech synthesis with automatic Roman-Urdu-to-Urdu lexicon normalization and frame-accurate 3D jaw viseme extraction.
        </p>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <div className="space-y-4 rounded-xl border border-slate-800 bg-[#111520] p-5">
          <h3 className="text-sm font-semibold text-white">Interactive Voice &amp; Viseme Synthesizer</h3>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Select Synthetic Voice</label>
            <select
              value={selectedVoice}
              onChange={(e) => setSelectedVoice(e.target.value)}
              className="w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs text-white"
            >
              {voices.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.name} — [{v.language.toUpperCase()} • {v.engine}]
                </option>
              ))}
            </select>
          </div>

          <div className="grid grid-cols-3 gap-3 text-xs">
            <div>
              <label className="block text-slate-400 mb-1">Speed ({speed.toFixed(2)}x)</label>
              <input
                type="range"
                min="0.6"
                max="1.6"
                step="0.05"
                value={speed}
                onChange={(e) => setSpeed(Number(e.target.value))}
                className="w-full accent-amber-500"
              />
            </div>
            <div>
              <label className="block text-slate-400 mb-1">Pitch ({pitch.toFixed(2)}x)</label>
              <input
                type="range"
                min="0.7"
                max="1.4"
                step="0.05"
                value={pitch}
                onChange={(e) => setPitch(Number(e.target.value))}
                className="w-full accent-amber-500"
              />
            </div>
            <div>
              <label className="block text-slate-400 mb-1">Emotion</label>
              <select
                value={emotion}
                onChange={(e) => setEmotion(e.target.value)}
                className="w-full rounded border border-slate-700 bg-slate-900 px-2 py-1 text-white"
              >
                {['neutral', 'calm', 'determined', 'angry', 'joyful', 'sad', 'fearful', 'surprised'].map((em) => (
                  <option key={em} value={em}>{em}</option>
                ))}
              </select>
            </div>
          </div>

          <div>
            <label className="block text-xs text-slate-400 mb-1">Test Dialogue Line (English, Roman Urdu, or اردو)</label>
            <textarea
              value={sampleText}
              onChange={(e) => setSampleText(e.target.value)}
              rows={3}
              className="w-full rounded-lg border border-slate-700 bg-[#0b0e16] p-3 text-sm text-white"
            />
          </div>

          <button
            onClick={handleSynthesize}
            disabled={loading}
            className="inline-flex items-center gap-2 rounded-lg bg-amber-500 px-4 py-2 text-xs font-bold text-slate-950 hover:bg-amber-400"
          >
            <Volume2 className="h-4 w-4" />
            {loading ? 'Synthesizing Locally...' : 'Synthesize Preview & Extract Visemes'}
          </button>

          {previewResult && (
            <div className="space-y-3 rounded-lg border border-slate-800 bg-[#0c101a] p-4 text-xs">
              <audio src={previewResult.audio_url} controls autoPlay className="w-full h-9" />
              <div className="text-slate-400">
                Engine: <strong className="text-amber-300">{previewResult.engine_used}</strong> • Detected Language:{' '}
                <strong className="text-white uppercase">{previewResult.language}</strong> • Duration:{' '}
                <strong className="text-white">{previewResult.duration_sec}s</strong>
              </div>
              {previewResult.normalized_text && (
                <div className="rounded bg-slate-900 p-2 text-slate-300">
                  <span className="text-slate-500">Normalized TTS Input: </span>
                  {previewResult.normalized_text}
                </div>
              )}
              <div>
                <div className="text-[11px] text-slate-400 mb-1">
                  3D Jaw Lip-Sync Viseme Envelope ({previewResult.viseme_frame_count} frames @ 24 FPS)
                </div>
                <div className="flex h-12 items-end gap-1 rounded bg-slate-950 p-2">
                  {(previewResult.viseme_sample || []).map((v: number, idx: number) => (
                    <div
                      key={idx}
                      style={{ height: `${Math.max(8, Math.round(v * 100))}%` }}
                      className="flex-1 rounded-t bg-amber-400/80"
                    />
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Honest Capability Matrix */}
        <div className="space-y-3 rounded-xl border border-slate-800 bg-[#111520] p-5">
          <h3 className="text-sm font-semibold text-white">Language &amp; Lip-Sync Capability Matrix</h3>
          <p className="text-xs text-slate-400">
            Transparent status of offline speech synthesis and 3D lip-sync per language. Zero unauthorized voice cloning is permitted.
          </p>
          <div className="space-y-3">
            {capabilities.map((cap, idx) => (
              <div key={idx} className="rounded-lg border border-slate-800 bg-[#151b29] p-3.5 text-xs space-y-1">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-white">{cap.language}</span>
                  <span className="rounded bg-emerald-500/15 px-2 py-0.5 text-[11px] text-emerald-300">
                    {cap.tts_status}
                  </span>
                </div>
                <div className="text-amber-300">{cap.tts_engine}</div>
                <div className="text-slate-300">Lip-Sync: {cap.lipsync_mode}</div>
                <div className="text-slate-400">{cap.naturalness_note}</div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

/* ==================== ENVIRONMENT STUDIO ==================== */
export const EnvironmentStudioView: React.FC<{
  project: ProjectSummary | null;
  environments: any[];
  onRefreshProject: () => Promise<void>;
  onNotify: (msg: string) => void;
}> = ({ project, environments, onRefreshProject, onNotify }) => {
  const [selectedEnv, setSelectedEnv] = useState('fortress');
  const [tod, setTod] = useState('sunset');
  const [weather, setWeather] = useState('clear');
  const [targetSceneId, setTargetSceneId] = useState(project?.scenes?.[0]?.id || '');
  const [previewUrl, setPreviewUrl] = useState('');

  useEffect(() => {
    if (project?.scenes?.[0]?.id && !targetSceneId) {
      setTargetSceneId(project.scenes[0].id);
    }
  }, [project?.id]);

  const triggerPreview = async (envId: string) => {
    setSelectedEnv(envId);
    const res = await api.post('/api/environments/preview-render', {
      environment_preset: envId,
      time_of_day: tod,
      weather,
      project_id: project?.id || null,
    });
    setPreviewUrl(res.expected_preview_url);
    onNotify(`Queued Blender 3D environment preview for '${envId}' (${tod}, ${weather}). Check Render Queue or wait ~3s.`);
  };

  const applyToScene = async (envId: string) => {
    if (!project || !targetSceneId) return;
    await api.patch(`/api/projects/${project.id}/scenes/${targetSceneId}`, {
      environment_preset: envId,
      time_of_day: tod,
      weather,
    });
    await onRefreshProject();
    onNotify(`Applied '${envId}' (${tod}, ${weather}) to scene.`);
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold text-white">3D Historical &amp; Cinematic Environment Studio</h2>
          <p className="text-xs text-slate-400">
            12 deterministic procedural 3D sets with recurring location seed lock, atmospheric weather, torches, and waving banners.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <select
            value={tod}
            onChange={(e) => setTod(e.target.value)}
            className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-white"
          >
            {['sunrise', 'day', 'sunset', 'night'].map((t) => (
              <option key={t} value={t}>Time: {t}</option>
            ))}
          </select>
          <select
            value={weather}
            onChange={(e) => setWeather(e.target.value)}
            className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-white"
          >
            {['clear', 'rain', 'fog', 'smoke', 'fire', 'dust'].map((w) => (
              <option key={w} value={w}>Weather: {w}</option>
            ))}
          </select>
          {project && (project.scenes || []).length > 0 && (
            <select
              value={targetSceneId}
              onChange={(e) => setTargetSceneId(e.target.value)}
              className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-white"
            >
              {(project.scenes || []).map((s) => (
                <option key={s.id} value={s.id}>Target: Scene {s.scene_index + 1} ({s.title})</option>
              ))}
            </select>
          )}
        </div>
      </div>

      {previewUrl && (
        <div className="rounded-xl border border-amber-500/30 bg-[#111520] p-4">
          <div className="flex items-center justify-between text-xs mb-2">
            <span className="font-semibold text-amber-300">Latest Requested 3D Environment Render ({selectedEnv})</span>
            <button
              onClick={() => setPreviewUrl(`${previewUrl.split('?')[0]}?t=${Date.now()}`)}
              className="rounded bg-slate-800 px-2.5 py-1 text-slate-200 hover:bg-slate-700"
            >
              Refresh Image
            </button>
          </div>
          <img
            src={previewUrl}
            alt="3D Environment Preview"
            onError={(e) => {
              (e.currentTarget as HTMLImageElement).style.opacity = '0.25';
            }}
            onLoad={(e) => {
              (e.currentTarget as HTMLImageElement).style.opacity = '1';
            }}
            className="max-h-72 rounded-lg border border-slate-800 mx-auto object-cover"
          />
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
        {environments.map((env) => (
          <div key={env.id} className="rounded-xl border border-slate-800 bg-[#121723] p-4 flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <Mountain className="h-4 w-4 text-amber-400" />
                <h3 className="font-semibold text-white text-sm">{env.label}</h3>
              </div>
              <span className="rounded bg-slate-800 px-2 py-0.5 text-[10px] uppercase text-slate-300">
                {env.category}
              </span>
            </div>
            <p className="text-xs text-slate-400">{env.description}</p>
            <div className="flex items-center gap-2 text-[11px] text-slate-400">
              <span>Palette:</span>
              <span style={{ backgroundColor: env.ground_color }} className="h-4 w-6 rounded border border-white/20" />
              <span style={{ backgroundColor: env.accent_color }} className="h-4 w-6 rounded border border-white/20" />
            </div>
            <div className="mt-auto flex gap-2 pt-1">
              <button
                onClick={() => triggerPreview(env.id)}
                className="flex-1 rounded-lg border border-slate-700 bg-slate-800 py-1.5 text-xs font-medium text-slate-200 hover:bg-slate-700"
              >
                Render 3D Preview
              </button>
              {project && targetSceneId && (
                <button
                  onClick={() => applyToScene(env.id)}
                  className="inline-flex items-center gap-1 rounded-lg bg-amber-500/20 border border-amber-500/40 px-3 py-1.5 text-xs font-semibold text-amber-300 hover:bg-amber-500/30"
                >
                  <Check className="h-3.5 w-3.5" /> Apply
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

/* ==================== ANIMATION & COMBAT STUDIO ==================== */
export const AnimationStudioView: React.FC<{
  project: ProjectSummary | null;
  onRefreshProject: () => Promise<void>;
  onNotify: (msg: string) => void;
}> = ({ project, onRefreshProject, onNotify }) => {
  const [animCatalog, setAnimCatalog] = useState<any>({ clips: [], attack_directions: [], defense_reactions: [] });
  const [selectedSceneId, setSelectedSceneId] = useState<string>('');
  const [positions, setPositions] = useState<any[]>([]);
  const [combat, setCombat] = useState<any>({ enabled: false, attack_direction: 'right_slash', defense_reaction: 'block', contact_frame_pct: 0.45, camera_angle_offset_deg: 18 });

  useEffect(() => {
    api.get('/api/animations').then(setAnimCatalog);
  }, []);

  useEffect(() => {
    const first = project?.scenes?.[0];
    if (first) {
      const target = (project?.scenes || []).find((s) => s.id === selectedSceneId) || first;
      setSelectedSceneId(target.id);
      setPositions(target.character_positions || []);
      setCombat(target.combat_choreography || { enabled: false, attack_direction: 'right_slash', defense_reaction: 'block', contact_frame_pct: 0.45, camera_angle_offset_deg: 18 });
    }
  }, [project?.id, selectedSceneId]);

  const handleSolveCollisions = async () => {
    const res = await api.post('/api/animations/solve-choreography', { positions });
    setPositions(res.character_positions || positions);
    onNotify('Collision-aware spacing solver separated overlapping character capsules.');
  };

  const handleSaveChoreography = async () => {
    if (!project || !selectedSceneId) return;
    await api.patch(`/api/projects/${project.id}/scenes/${selectedSceneId}`, {
      character_positions: positions,
      combat_choreography: combat,
      actions: positions.map((p) => p.action_clip),
    });
    await onRefreshProject();
    onNotify('Saved 3D animation clips & combat choreography to scene.');
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold text-white">Real 3D Animation &amp; Combat Choreography Studio</h2>
          <p className="text-xs text-slate-400">
            Configure articulated Blender 3D skeletal actions, spatial coordinates, collision-safe spacing, and combat contact timing.
          </p>
        </div>
        {project && (project.scenes || []).length > 0 && (
          <select
            value={selectedSceneId}
            onChange={(e) => setSelectedSceneId(e.target.value)}
            className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs text-white"
          >
            {(project.scenes || []).map((s) => (
              <option key={s.id} value={s.id}>
                Scene {s.scene_index + 1}: {s.title}
              </option>
            ))}
          </select>
        )}
      </div>

      {!project ? (
        <div className="rounded-xl border border-slate-800 bg-[#111520] p-6 text-xs text-slate-400">
          Select a project to edit per-scene character choreography, or inspect the 20 supported 3D action clips below.
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-2">
          {/* Spatial Stage & Character Action Clips */}
          <div className="space-y-4 rounded-xl border border-slate-800 bg-[#111520] p-5">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-white">Character Blocking &amp; Action Clips</h3>
              <button
                onClick={handleSolveCollisions}
                className="inline-flex items-center gap-1 rounded bg-slate-800 px-2.5 py-1 text-xs text-amber-300 hover:bg-slate-700"
              >
                <ShieldCheck className="h-3.5 w-3.5" /> Enforce Collision-Free Spacing
              </button>
            </div>

            {positions.map((pos, idx) => (
              <div key={idx} className="rounded-lg border border-slate-800 bg-[#161c2b] p-3 space-y-2 text-xs">
                <div className="font-semibold text-amber-300">{pos.character_name}</div>
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                  <div>
                    <label className="block text-[11px] text-slate-400">Action Clip</label>
                    <select
                      value={pos.action_clip}
                      onChange={(e) => {
                        const next = [...positions];
                        next[idx] = { ...next[idx], action_clip: e.target.value };
                        setPositions(next);
                      }}
                      className="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1 text-white"
                    >
                      {(animCatalog.clips || []).map((c: any) => (
                        <option key={c.id} value={c.id}>{c.label}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-[11px] text-slate-400">Stage X (m)</label>
                    <input
                      type="number"
                      step="0.2"
                      value={pos.x}
                      onChange={(e) => {
                        const next = [...positions];
                        next[idx] = { ...next[idx], x: Number(e.target.value) };
                        setPositions(next);
                      }}
                      className="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1 text-white"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] text-slate-400">Depth Y (m)</label>
                    <input
                      type="number"
                      step="0.2"
                      value={pos.y}
                      onChange={(e) => {
                        const next = [...positions];
                        next[idx] = { ...next[idx], y: Number(e.target.value) };
                        setPositions(next);
                      }}
                      className="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1 text-white"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] text-slate-400">Expression</label>
                    <select
                      value={pos.expression || 'determined'}
                      onChange={(e) => {
                        const next = [...positions];
                        next[idx] = { ...next[idx], expression: e.target.value };
                        setPositions(next);
                      }}
                      className="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1 text-white"
                    >
                      {(animCatalog.expressions || ['determined', 'angry', 'calm', 'joyful']).map((ex: string) => (
                        <option key={ex} value={ex}>{ex}</option>
                      ))}
                    </select>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* Combat Choreography Timing */}
          <div className="space-y-4 rounded-xl border border-slate-800 bg-[#111520] p-5">
            <div className="flex items-center justify-between">
              <h3 className="flex items-center gap-2 text-sm font-semibold text-white">
                <Swords className="h-4 w-4 text-red-400" /> Combat Choreography Controls
              </h3>
              <label className="flex items-center gap-2 text-xs text-slate-300">
                <input
                  type="checkbox"
                  checked={Boolean(combat.enabled)}
                  onChange={(e) => setCombat({ ...combat, enabled: e.target.checked })}
                />
                Enable Choreographed Exchange
              </label>
            </div>

            <div className="grid grid-cols-2 gap-3 text-xs">
              <div>
                <label className="block text-slate-400 mb-1">Attack Direction</label>
                <select
                  value={combat.attack_direction || 'right_slash'}
                  onChange={(e) => setCombat({ ...combat, attack_direction: e.target.value })}
                  className="w-full rounded border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-white"
                >
                  {(animCatalog.attack_directions || []).map((d: string) => (
                    <option key={d} value={d}>{d}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-slate-400 mb-1">Defender Reaction</label>
                <select
                  value={combat.defense_reaction || 'block'}
                  onChange={(e) => setCombat({ ...combat, defense_reaction: e.target.value })}
                  className="w-full rounded border border-slate-700 bg-slate-900 px-2.5 py-1.5 text-white"
                >
                  {(animCatalog.defense_reactions || []).map((r: string) => (
                    <option key={r} value={r}>{r}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="block text-slate-400 mb-1">
                  Primary Contact Beat ({Math.round((combat.contact_frame_pct || 0.45) * 100)}% of scene)
                </label>
                <input
                  type="range"
                  min="0.2"
                  max="0.7"
                  step="0.05"
                  value={combat.contact_frame_pct || 0.45}
                  onChange={(e) => setCombat({ ...combat, contact_frame_pct: Number(e.target.value) })}
                  className="w-full accent-amber-500"
                />
              </div>
              <div>
                <label className="block text-slate-400 mb-1">
                  Camera Angle Offset ({combat.camera_angle_offset_deg || 18}&deg;)
                </label>
                <input
                  type="range"
                  min="-45"
                  max="45"
                  step="3"
                  value={combat.camera_angle_offset_deg || 18}
                  onChange={(e) => setCombat({ ...combat, camera_angle_offset_deg: Number(e.target.value) })}
                  className="w-full accent-amber-500"
                />
              </div>
            </div>

            <button
              onClick={handleSaveChoreography}
              className="w-full rounded-lg bg-amber-500 py-2 text-xs font-bold text-slate-950 hover:bg-amber-400"
            >
              Save Animation &amp; Combat Choreography to Scene
            </button>
          </div>
        </div>
      )}

      {/* Full Supported 3D Actions Reference */}
      <div className="rounded-xl border border-slate-800 bg-[#111520] p-4">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-3">
          20 Built-In Blender 3D Skeletal Action Clips
        </h3>
        <div className="flex flex-wrap gap-2">
          {(animCatalog.clips || []).map((c: any) => (
            <span key={c.id} className="rounded-md border border-slate-800 bg-slate-900 px-2.5 py-1 text-xs text-slate-300">
              {c.label} <span className="text-[10px] text-amber-400">({c.category})</span>
            </span>
          ))}
        </div>
      </div>
    </div>
  );
};
