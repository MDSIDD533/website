import React, { useCallback, useEffect, useState } from 'react';
import {
  LayoutDashboard,
  PlusSquare,
  FileText,
  Layers,
  Users,
  Mic2,
  Mountain,
  Swords,
  SlidersHorizontal,
  ListChecks,
  Film,
  Boxes,
  Cpu,
  Settings,
  Menu,
  X,
  CheckCircle2,
  Sparkles,
} from 'lucide-react';
import { api, createJobsWebSocket } from './api';
import { JobItem, NavSection, ProjectSummary, SceneItem } from './types';
import { CreateProjectView, DashboardView } from './views/DashboardAndCreate';
import { ScriptEditorView, StoryboardView } from './views/ScriptAndStoryboard';
import {
  AnimationStudioView,
  CharacterStudioView,
  EnvironmentStudioView,
  VoiceStudioView,
} from './views/CreativeStudios';
import {
  RenderQueueView,
  SceneTimelineView,
  VideoLibraryView,
} from './views/TimelineQueueLibrary';
import {
  HardwareMonitorView,
  ModelManagerView,
  ProjectSettingsView,
} from './views/SystemViews';

const NAV_ITEMS: { id: NavSection; label: string; icon: React.ComponentType<any> }[] = [
  { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
  { id: 'create', label: 'Create New Video', icon: PlusSquare },
  { id: 'script', label: 'Script Editor', icon: FileText },
  { id: 'storyboard', label: 'Storyboard', icon: Layers },
  { id: 'characters', label: 'Character Studio', icon: Users },
  { id: 'voices', label: 'Voice Studio', icon: Mic2 },
  { id: 'environments', label: 'Environment Studio', icon: Mountain },
  { id: 'animations', label: 'Animation Studio', icon: Swords },
  { id: 'timeline', label: 'Scene Timeline', icon: SlidersHorizontal },
  { id: 'queue', label: 'Render Queue', icon: ListChecks },
  { id: 'library', label: 'Video Library', icon: Film },
  { id: 'models', label: 'AI Model Manager', icon: Boxes },
  { id: 'hardware', label: 'Hardware Monitor', icon: Cpu },
  { id: 'settings', label: 'Project Settings', icon: Settings },
];

export const App: React.FC = () => {
  const [nav, setNav] = useState<NavSection>('dashboard');
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [activeProject, setActiveProject] = useState<ProjectSummary | null>(null);
  const [jobs, setJobs] = useState<JobItem[]>([]);
  const [wsConnected, setWsConnected] = useState(false);

  const [hardware, setHardware] = useState<any>(null);
  const [storage, setStorage] = useState<any>(null);
  const [voices, setVoices] = useState<any[]>([]);
  const [capabilities, setCapabilities] = useState<any[]>([]);
  const [musicMoods, setMusicMoods] = useState<any[]>([]);
  const [environments, setEnvironments] = useState<any[]>([]);
  const [cameraShots, setCameraShots] = useState<any[]>([]);
  const [cameraMovements, setCameraMovements] = useState<string[]>([]);

  const [toast, setToast] = useState<string>('');

  const notify = useCallback((msg: string) => {
    setToast(msg);
    window.setTimeout(() => {
      setToast((prev) => (prev === msg ? '' : prev));
    }, 4500);
  }, []);

  const loadProjects = useCallback(async (selectId?: string) => {
    const res = await api.get('/api/projects');
    const list: ProjectSummary[] = res.projects || [];
    setProjects(list);
    const targetId = selectId || activeProject?.id || list[0]?.id;
    if (targetId && list.some((p) => p.id === targetId)) {
      const full = await api.get<ProjectSummary>(`/api/projects/${targetId}`);
      setActiveProject(full);
    } else if (list.length === 0) {
      setActiveProject(null);
    }
  }, [activeProject?.id]);

  const loadSystemAndCatalogs = useCallback(async () => {
    const [hw, st, vc, env, jb] = await Promise.all([
      api.get('/api/system/hardware'),
      api.get('/api/system/storage'),
      api.get('/api/voices'),
      api.get('/api/environments'),
      api.get('/api/jobs'),
    ]);
    setHardware(hw);
    setStorage(st);
    setVoices(vc.voices || []);
    setCapabilities(vc.lipsync_capabilities || []);
    setMusicMoods(vc.music_moods || []);
    setEnvironments(env.environments || []);
    setCameraShots(env.camera_shots || []);
    setCameraMovements(env.camera_movements || []);
    setJobs(jb.jobs || []);
  }, []);

  useEffect(() => {
    loadSystemAndCatalogs();
    loadProjects();
  }, []);

  // Live WebSocket job progress stream
  useEffect(() => {
    const disconnect = createJobsWebSocket(
      (event) => {
        if (event.type === 'initial_jobs') {
          setJobs(event.jobs || []);
        } else if (event.type === 'job_update' && event.job) {
          const updatedJob: JobItem = event.job;
          setJobs((prev) => {
            const exists = prev.some((j) => j.id === updatedJob.id);
            return exists
              ? prev.map((j) => (j.id === updatedJob.id ? updatedJob : j))
              : [updatedJob, ...prev];
          });
          if (updatedJob.status === 'completed' || updatedJob.status === 'failed') {
            loadProjects(updatedJob.project_id || undefined);
            api.get('/api/system/storage').then(setStorage).catch(() => {});
          }
        }
      },
      setWsConnected
    );
    return disconnect;
  }, [loadProjects]);

  const handleSelectProject = async (id: string, targetNav?: NavSection) => {
    const full = await api.get<ProjectSummary>(`/api/projects/${id}`);
    setActiveProject(full);
    if (targetNav) setNav(targetNav);
  };

  const handleQuickCreateSample = async (sampleKey: string) => {
    const sampleData = await api.get('/api/projects/samples');
    const s = sampleData.samples?.[sampleKey];
    if (!s) return;
    const created = await api.post<ProjectSummary>('/api/projects', {
      title: s.title,
      description: s.description,
      language: s.language,
      genre: s.genre || 'historical',
      historical_accuracy_mode: true,
      target_duration_sec: 9.0,
      aspect_ratio: '16:9',
      resolution: '720p',
      fps: 24,
      quality_profile: hardware?.recommended_mode || 'low_resource',
      num_scenes_target: 3,
      script_text: s.script,
      auto_generate_storyboard: true,
    });
    setActiveProject(created);
    await loadProjects(created.id);
    setNav('storyboard');
    notify(`Created "${created.title}" with ${created.scenes?.length || 0} storyboard scenes.`);
  };

  const handleRenderScene = async (sceneId: string) => {
    if (!activeProject) return;
    await api.post('/api/jobs/render-scene', {
      project_id: activeProject.id,
      scene_id: sceneId,
    });
    notify('Scene render queued! Track live raytracing frames in Render Queue.');
    setNav('queue');
  };

  const handleRenderSelected = async (sceneIds: string[]) => {
    if (!activeProject) return;
    await api.post('/api/jobs/render-selected', {
      project_id: activeProject.id,
      scene_ids: sceneIds,
    });
    notify(`Queued ${sceneIds.length} selected scene(s) for 3D rendering.`);
    setNav('queue');
  };

  const handleRenderFullProject = async (forceRerender = false) => {
    if (!activeProject) return;
    await api.post('/api/jobs/render-project', {
      project_id: activeProject.id,
      force_rerender: forceRerender,
    });
    notify('Queued full chronological 3D MP4 production! Opening Render Queue.');
    setNav('queue');
  };

  const runningCount = jobs.filter((j) => j.status === 'running' || j.status === 'queued').length;

  return (
    <div className="flex min-h-screen bg-[#090b10] text-slate-100">
      {/* Desktop Sidebar */}
      <aside className="hidden w-64 shrink-0 border-r border-slate-800/90 bg-[#0d1018] lg:flex lg:flex-col">
        <div className="border-b border-slate-800/80 px-5 py-4">
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-amber-400 to-amber-600 text-slate-950 font-black">
              S
            </div>
            <div>
              <div className="text-sm font-extrabold tracking-wide text-white">SIDD AI VIDEO</div>
              <div className="text-[10px] font-semibold tracking-widest text-amber-400">3D STUDIO LOCAL</div>
            </div>
          </div>
        </div>

        <nav className="flex-1 space-y-0.5 overflow-y-auto p-3">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const active = nav === item.id;
            return (
              <button
                key={item.id}
                onClick={() => setNav(item.id)}
                className={`flex w-full items-center justify-between rounded-lg px-3 py-2 text-xs font-medium transition ${
                  active
                    ? 'bg-amber-500/15 text-amber-300 border border-amber-500/30'
                    : 'text-slate-400 hover:bg-slate-800/60 hover:text-slate-200'
                }`}
              >
                <span className="flex items-center gap-2.5">
                  <Icon className={`h-4 w-4 ${active ? 'text-amber-400' : 'text-slate-500'}`} />
                  {item.label}
                </span>
                {item.id === 'queue' && runningCount > 0 && (
                  <span className="rounded-full bg-amber-500 px-1.5 py-0.5 text-[10px] font-bold text-slate-950">
                    {runningCount}
                  </span>
                )}
              </button>
            );
          })}
        </nav>

        <div className="border-t border-slate-800/80 p-3 text-[11px] text-slate-400">
          <div className="flex items-center justify-between">
            <span>Offline Core</span>
            <span className="text-emerald-400 font-semibold">Active</span>
          </div>
          <div className="mt-1 truncate">
            Mode: <span className="text-amber-300 capitalize">{(hardware?.active_mode || 'low_resource').replace('_', ' ')}</span>
          </div>
        </div>
      </aside>

      {/* Mobile Drawer */}
      {mobileMenuOpen && (
        <div className="fixed inset-0 z-50 flex lg:hidden">
          <div className="w-64 bg-[#0d1018] border-r border-slate-800 p-4 flex flex-col">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <span className="font-bold text-sm text-amber-400">SIDD AI VIDEO STUDIO</span>
              <button onClick={() => setMobileMenuOpen(false)}>
                <X className="h-5 w-5 text-slate-400" />
              </button>
            </div>
            <div className="mt-3 space-y-1 overflow-y-auto">
              {NAV_ITEMS.map((item) => {
                const Icon = item.icon;
                return (
                  <button
                    key={item.id}
                    onClick={() => {
                      setNav(item.id);
                      setMobileMenuOpen(false);
                    }}
                    className={`flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-xs font-medium ${
                      nav === item.id ? 'bg-amber-500/15 text-amber-300' : 'text-slate-300'
                    }`}
                  >
                    <Icon className="h-4 w-4" />
                    {item.label}
                  </button>
                );
              })}
            </div>
          </div>
          <div className="flex-1 bg-black/60" onClick={() => setMobileMenuOpen(false)} />
        </div>
      )}

      {/* Main Content Area */}
      <div className="flex flex-1 flex-col min-w-0">
        {/* Top Header */}
        <header className="sticky top-0 z-30 flex flex-wrap items-center justify-between gap-3 border-b border-slate-800/80 bg-[#0d1018]/95 px-4 py-3 backdrop-blur">
          <div className="flex items-center gap-3">
            <button
              onClick={() => setMobileMenuOpen(true)}
              className="rounded-lg border border-slate-700 p-1.5 text-slate-300 lg:hidden"
            >
              <Menu className="h-4 w-4" />
            </button>
            <div className="flex items-center gap-2 text-xs">
              <span className="text-slate-400 hidden sm:inline">Active Project:</span>
              {projects.length > 0 ? (
                <select
                  value={activeProject?.id || ''}
                  onChange={(e) => handleSelectProject(e.target.value)}
                  className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs font-medium text-white"
                >
                  {projects.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.title} ({p.language.toUpperCase()})
                    </option>
                  ))}
                </select>
              ) : (
                <span className="text-slate-500">None yet</span>
              )}
              {activeProject && (
                <span className="hidden md:inline-flex items-center gap-1 rounded bg-emerald-500/10 px-2 py-0.5 text-[11px] text-emerald-300">
                  <CheckCircle2 className="h-3 w-3" /> Auto-Saved
                </span>
              )}
            </div>
          </div>

          <div className="flex items-center gap-2.5 text-xs">
            {runningCount > 0 && (
              <button
                onClick={() => setNav('queue')}
                className="inline-flex items-center gap-1.5 rounded-full border border-amber-500/40 bg-amber-500/15 px-3 py-1 text-amber-300 animate-pulse"
              >
                <Sparkles className="h-3.5 w-3.5" />
                {runningCount} Job Rendering...
              </button>
            )}
            <span className="hidden sm:inline text-slate-400">
              Free Disk: <strong className="text-slate-200">{storage ? `${storage.disk_free_gb} GB` : '...'}</strong>
            </span>
          </div>
        </header>

        {toast && (
          <div className="mx-4 mt-3 rounded-lg border border-amber-500/40 bg-amber-500/15 px-4 py-2 text-xs font-medium text-amber-200">
            {toast}
          </div>
        )}

        <main className="flex-1 p-4 sm:p-6 max-w-7xl w-full mx-auto">
          {nav === 'dashboard' && (
            <DashboardView
              projects={projects}
              activeProject={activeProject}
              jobs={jobs}
              hardware={hardware}
              storage={storage}
              onSelectProject={handleSelectProject}
              onNavigate={setNav}
              onQuickCreateSample={handleQuickCreateSample}
            />
          )}

          {nav === 'create' && (
            <CreateProjectView
              voices={voices}
              musicMoods={musicMoods}
              hardware={hardware}
              jobs={jobs}
              activeProject={activeProject}
              onCreated={async (created, navigateToStoryboard = true) => {
                setActiveProject(created);
                await loadProjects(created.id);
                if (navigateToStoryboard) {
                  setNav('storyboard');
                  notify(`Storyboard generated with ${created.scenes?.length || 0} scenes.`);
                }
              }}
              onJobQueued={(newJob) => {
                setJobs((prev) => [newJob, ...prev.filter((j) => j.id !== newJob.id)]);
                notify(`Video generation started (${newJob.id}). Watch live progress right below!`);
              }}
              onNavigate={setNav}
            />
          )}

          {nav === 'script' && (
            <ScriptEditorView
              project={activeProject}
              onProjectUpdated={(updated) => {
                setActiveProject(updated);
                loadProjects(updated.id);
              }}
              onNavigate={setNav}
            />
          )}

          {nav === 'storyboard' && (
            <StoryboardView
              project={activeProject}
              environments={environments}
              cameraShots={cameraShots}
              cameraMovements={cameraMovements}
              voices={voices}
              onSceneUpdated={(updatedScene: SceneItem) => {
                if (!activeProject) return;
                setActiveProject({
                  ...activeProject,
                  scenes: (activeProject.scenes || []).map((s) =>
                    s.id === updatedScene.id ? updatedScene : s
                  ),
                });
              }}
              onRenderScene={handleRenderScene}
              onRenderFullProject={handleRenderFullProject}
              onNavigate={setNav}
            />
          )}

          {nav === 'characters' && (
            <CharacterStudioView
              project={activeProject}
              voices={voices}
              onRefreshProject={() => loadProjects(activeProject?.id)}
              onNotify={notify}
            />
          )}

          {nav === 'voices' && (
            <VoiceStudioView voices={voices} capabilities={capabilities} />
          )}

          {nav === 'environments' && (
            <EnvironmentStudioView
              project={activeProject}
              environments={environments}
              onRefreshProject={() => loadProjects(activeProject?.id)}
              onNotify={notify}
            />
          )}

          {nav === 'animations' && (
            <AnimationStudioView
              project={activeProject}
              onRefreshProject={() => loadProjects(activeProject?.id)}
              onNotify={notify}
            />
          )}

          {nav === 'timeline' && (
            <SceneTimelineView
              project={activeProject}
              onRefreshProject={() => loadProjects(activeProject?.id)}
              onRenderSelected={handleRenderSelected}
              onRenderFull={handleRenderFullProject}
              onNavigate={setNav}
            />
          )}

          {nav === 'queue' && (
            <RenderQueueView
              jobs={jobs}
              wsConnected={wsConnected}
              onRefreshJobs={async () => {
                const jb = await api.get('/api/jobs');
                setJobs(jb.jobs || []);
              }}
            />
          )}

          {nav === 'library' && <VideoLibraryView />}

          {nav === 'models' && <ModelManagerView onNotify={notify} />}

          {nav === 'hardware' && (
            <HardwareMonitorView
              hardware={hardware}
              onModeChange={async (mode) => {
                await api.patch('/api/system/settings', { performance_mode: mode });
                const hw = await api.get('/api/system/hardware');
                setHardware(hw);
                notify(`Switched studio performance mode to ${mode.replace('_', ' ')}.`);
              }}
            />
          )}

          {nav === 'settings' && (
            <ProjectSettingsView
              project={activeProject}
              storage={storage}
              onRefreshAll={async () => {
                await loadSystemAndCatalogs();
                await loadProjects();
              }}
              onProjectDeleted={async () => {
                setActiveProject(null);
                await loadProjects();
                await loadSystemAndCatalogs();
                setNav('dashboard');
              }}
              onNotify={notify}
            />
          )}
        </main>
      </div>
    </div>
  );
};
