export type NavSection =
  | 'dashboard'
  | 'studio'
  | 'create'
  | 'script'
  | 'storyboard'
  | 'characters'
  | 'voices'
  | 'environments'
  | 'animations'
  | 'timeline'
  | 'queue'
  | 'library'
  | 'models'
  | 'hardware'
  | 'settings';

export interface DialogueLine {
  id?: string;
  speaker: string;
  voice_id: string;
  text: string;
  emotion: string;
  speed?: number;
  pitch?: number;
  pause_after_sec?: number;
}

export interface CharacterPosition {
  character_name: string;
  x: number;
  y: number;
  z: number;
  yaw_deg: number;
  action_clip: string;
  expression?: string;
}

export interface CombatChoreography {
  enabled: boolean;
  attacker?: string;
  defender?: string;
  attack_direction?: string;
  defense_reaction?: string;
  strike_distance_m?: number;
  contact_frame_pct?: number;
  secondary_exchange_pct?: number;
  camera_angle_offset_deg?: number;
  collision_guard_active?: boolean;
}

export interface SceneItem {
  id: string;
  project_id: string;
  scene_index: number;
  title: string;
  summary: string;
  location_name: string;
  environment_preset: string;
  time_of_day: string;
  weather: string;
  lighting_style: string;
  camera_shot: string;
  camera_movement: string;
  duration_sec: number;
  transition_type: string;
  characters_present: string[];
  character_positions: CharacterPosition[];
  actions: string[];
  combat_choreography: CombatChoreography;
  props: string[];
  narration_text: string;
  narration_voice_id: string;
  dialogue: DialogueLine[];
  audio_cues: Record<string, any>;
  historical_notes: {
    mode_enabled?: boolean;
    verified_period_elements?: string[];
    dramatized_fictional_elements?: string[];
  };
  generation_status: string;
  thumbnail_path: string;
  rendered_video_path: string;
  audio_mix_path: string;
  subtitle_path: string;
  error_message: string;
  render_metrics: Record<string, any>;
  created_at?: string;
  updated_at?: string;
}

export interface CharacterProfile {
  id: string;
  project_id: string | null;
  name: string;
  role: string;
  appearance_description: string;
  face_reference_path: string;
  hair_style: string;
  hair_color: string;
  skin_tone: string;
  outfit_preset: string;
  outfits: string[];
  active_outfit: string;
  body_proportions: { height_scale: number; shoulder_width: number; build: string };
  color_palette: string[];
  personality: string;
  default_voice_id: string;
  language: string;
  rig_type: string;
  animations: Record<string, any>;
  expressions: Record<string, string>;
  props: string[];
  approved: boolean;
  preview_image_path: string;
  identity_seed: number;
  consistency_method: string;
}

export interface ProjectSummary {
  id: string;
  title: string;
  description: string;
  language: string;
  visual_style: string;
  genre: string;
  historical_accuracy_mode: boolean;
  target_duration_sec: number;
  aspect_ratio: string;
  resolution: string;
  fps: number;
  quality_profile: string;
  num_scenes_target: number;
  script_text: string;
  narration_prefs: { enabled: boolean; voice_id: string };
  dialogue_prefs: { enabled: boolean; subtitles: boolean; burn_in_captions: boolean };
  music_prefs: { enabled: boolean; mood: string; volume: number };
  analysis: Record<string, any>;
  export_status: string;
  latest_export_path: string;
  render_report: Record<string, any>;
  save_status: string;
  scene_count?: number;
  rendered_scene_count?: number;
  cover_thumbnail_path?: string;
  scenes?: SceneItem[];
  characters?: CharacterProfile[];
  workload_warnings?: string[];
  created_at: string;
  updated_at: string;
}

export interface JobItem {
  id: string;
  project_id: string | null;
  job_type: string;
  status: string;
  current_stage: string;
  progress_pct: number | null;
  progress_measurable: boolean;
  payload: Record<string, any>;
  output_paths: Record<string, any>;
  logs: string[];
  error_details: string;
  retry_count: number;
  worker_pid: number | null;
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export type MotionTemplateId = 'title' | 'data' | 'shape' | 'quote' | 'outro';
export type MotionJobMode = 'build_only' | 'render';
export type MotionJobQuality = 'draft' | 'standard' | 'high';

export interface MotionTemplateInfo {
  id: MotionTemplateId;
  label: string;
  description: string;
  hyperframes_version: string;
  request_fields: string[];
  default_request: Record<string, any>;
  default_variables: Record<string, any>;
  variable_schema: Array<Record<string, any>>;
}

export interface MotionParsedScene {
  scene_id: number;
  location: string;
  time_of_day: string;
  characters: string[];
  actions: string[];
  dialogue: Array<{ speaker: string; line: string }>;
  duration_sec: number;
}

export interface MotionPreview {
  template: MotionTemplateId;
  scenes: MotionParsedScene[];
  scene_count: number;
  request: Record<string, any>;
  variables: Record<string, any>;
}

export type MotionSelectionId = MotionTemplateId | 'auto';

export interface MotionAutoClipPlan {
  clip_id: string;
  scene_id: number;
  template: MotionTemplateId;
  sentence_text: string;
  reason: string;
  reason_codes: string[];
  request: Record<string, any>;
  scene_duration_sec: number;
  duration_sec: number;
  warnings: string[];
}

export interface MotionAutoPlan {
  planner_version: string;
  policy: string;
  script_text: string;
  scenes: MotionParsedScene[];
  clips: MotionAutoClipPlan[];
  scene_count: number;
  clip_count: number;
  total_duration_sec: number;
  warnings: string[];
}

export interface MotionAutoPreview {
  template: 'auto';
  mode: MotionJobMode;
  fps: number;
  quality: MotionJobQuality;
  scenes: MotionParsedScene[];
  scene_count: number;
  clips: MotionAutoClipPlan[];
  clip_count: number;
  total_duration_sec: number;
  plan: MotionAutoPlan;
}

export interface ModelItem {
  id: string;
  name: string;
  purpose: string;
  category: string;
  version: string;
  license: string;
  commercial_use: boolean;
  attribution_required: boolean;
  download_size_mb: number;
  required_storage_mb: number;
  min_ram_gb: number;
  min_vram_mb: number;
  requires_gpu: boolean;
  internet_required_to_run: boolean;
  internet_required_to_install: boolean;
  builtin: boolean;
  supported_languages: string[];
  supported_tasks: string[];
  implementation_status: string;
  notes: string;
  installed: boolean;
  active: boolean;
  compatibility_status: 'compatible' | 'warning' | 'incompatible';
  compatibility_notes: string[];
  model_directory: string;
  verified_sha256: string;
  last_verified_at: string;
}
