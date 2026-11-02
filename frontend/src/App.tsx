import React, { useCallback, useEffect, useState } from 'react';
import {
  LayoutDashboard,
  Clapperboard,
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
import { MotionStudioView } from './views/MotionStudio';
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
  { id: 'studio', label: 'Motion Studio', icon: Clapperboard },
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

const MOBILE_NAV_ITEMS: { id: NavSection; label: string; icon: React.ComponentType<any> }[] = [
  { id: 'dashboard', label: 'Home', icon: LayoutDashboard },
  { id: 'studio', label: 'Studio', icon: Clapperboard },
  { id: 'create', label: 'Create', icon: PlusSquare },
  { id: 'queue', label: 'Queue', icon: ListChecks },
];

const navFromPath = (): NavSection =>
  typeof window !== 'undefined' && window.location.pathname === '/studio' ? 'studio' : 'dashboard';

export const App: React.FC = () => {
  const [nav, setNavState] = useState<NavSection>(navFromPath);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  const setNav = useCallback((next: NavSection) => {
    setNavState(next);
    if (typeof window !== 'undefined') {
      const targetPath = next === 'studio' ? '/studio' : '/';
      if (window.location.pathname !== targetPath) {
        window.history.pushState({}, '', targetPath);
      }
    }
  }, []);

  useEffect(() => {
    const onPopState = () => setNavState(navFromPath());
    window.addEventListener('popstate', onPopState);
    return () => window.removeEventListener('popstate', onPopState);
  }, []);

  useEffect(() => {
    if (!mobileMenuOpen) return;
    const previousOverflow = document.body.style.overflow;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setMobileMenuOpen(false);
    };
    document.body.style.overflow = 'hidden';
    window.addEventListener('keydown', onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener('keydown', onKeyDown);
    };
  }, [mobileMenuOpen]);

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

  const upsertJob = useCallback((updatedJob: JobItem) => {
    setJobs((prev) => {
      const exists = prev.some((job) => job.id === updatedJob.id);
      return exists
        ? prev.map((job) => (job.id === updatedJob.id ? updatedJob : job))
        : [updatedJob, ...prev];
    });
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
    <div className="flex min-h-[100dvh] w-full overflow-x-clip bg-[#090b10] text-slate-100">
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
        <div className="fixed inset-0 z-50 flex lg:hidden" role="dialog" aria-modal="true" aria-label="All studio sections">
          <button
            type="button"
            aria-label="Close navigation menu"
            className="absolute inset-0 bg-black/70"
            onClick={() => setMobileMenuOpen(false)}
          />
          <div className="relative flex h-full w-[min(20rem,85vw)] flex-col overflow-y-auto border-r border-slate-800 bg-[#0d1018] px-4 pb-[max(1rem,env(safe-area-inset-bottom))] pt-[max(1rem,env(safe-area-inset-top))] shadow-2xl">
            <div className="flex items-center justify-between gap-3 border-b border-slate-800 pb-3">
              <span className="text-sm font-bold text-amber-400">SIDD AI VIDEO STUDIO</span>
              <button
                type="button"
                aria-label="Close navigation menu"
                onClick={() => setMobileMenuOpen(false)}
                className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-slate-700 text-slate-300"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <nav className="mt-3 space-y-1" aria-label="All sections">
              {NAV_ITEMS.map((item) => {
                const Icon = item.icon;
                return (
                  <button
                    key={item.id}
                    type="button"
                    aria-current={nav === item.id ? 'page' : undefined}
                    onClick={() => {
                      setNav(item.id);
                      setMobileMenuOpen(false);
                    }}
                    className={`flex min-h-11 w-full items-center justify-between gap-2.5 rounded-lg px-3 py-3 text-left text-sm font-medium ${
                      nav === item.id ? 'bg-amber-500/15 text-amber-300' : 'text-slate-300 hover:bg-slate-800/70'
                    }`}
                  >
                    <span className="flex min-w-0 items-center gap-2.5">
                      <Icon className="h-5 w-5 shrink-0" />
                      <span className="truncate">{item.label}</span>
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
          </div>
        </div>
      )}

      {/* Main Content Area */}
      <div className="flex flex-1 flex-col min-w-0">
        {/* Top Header */}
        <header className="sticky top-0 z-30 flex flex-nowrap items-center justify-between gap-2 border-b border-slate-800/80 bg-[#0d1018]/95 px-3 py-2.5 backdrop-blur sm:gap-3 sm:px-4">
          <div className="flex min-w-0 flex-1 items-center gap-2 sm:gap-3">
            <button
              type="button"
              aria-label="Open navigation menu"
              aria-haspopup="dialog"
              aria-expanded={mobileMenuOpen}
              onClick={() => setMobileMenuOpen(true)}
              className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-slate-700 text-slate-300 lg:hidden"
            >
              <Menu className="h-5 w-5" />
            </button>
            <div className="flex min-w-0 flex-1 items-center gap-2 text-xs">
              <label htmlFor="active-project" className="hidden shrink-0 text-slate-400 sm:inline">
                Active Project:
              </label>
              {projects.length > 0 ? (
                <select
                  id="active-project"
                  value={activeProject?.id || ''}
                  onChange={(e) => handleSelectProject(e.target.value)}
                  className="h-11 min-w-0 max-w-[58vw] flex-1 truncate rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 font-medium text-white sm:max-w-xs sm:flex-none"
                >
                  {projects.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.title} ({p.language.toUpperCase()})
                    </option>
                  ))}
                </select>
              ) : (
                <span className="truncate text-slate-500">No project yet</span>
              )}
              {activeProject && (
                <span className="hidden shrink-0 items-center gap-1 rounded bg-emerald-500/10 px-2 py-0.5 text-[11px] text-emerald-300 lg:inline-flex">
                  <CheckCircle2 className="h-3 w-3" /> Auto-Saved
                </span>
              )}
            </div>
          </div>

          <div className="flex shrink-0 items-center gap-2.5 text-xs">
            {runningCount > 0 && (
              <button
                type="button"
                aria-label={`${runningCount} jobs rendering. Open render queue.`}
                onClick={() => setNav('queue')}
                className="inline-flex min-h-11 items-center gap-1.5 rounded-full border border-amber-500/40 bg-amber-500/15 px-3 py-2 text-amber-300 animate-pulse"
              >
                <Sparkles className="h-4 w-4" />
                <span>{runningCount}</span>
                <span className="hidden min-[430px]:inline">rendering</span>
              </button>
            )}
            <span className="hidden text-slate-400 md:inline">
              Free Disk: <strong className="text-slate-200">{storage ? `${storage.disk_free_gb} GB` : '...'}</strong>
            </span>
          </div>
        </header>

        {toast && (
          <div
            role="status"
            aria-live="polite"
            className="mx-3 mt-3 rounded-lg border border-amber-500/40 bg-amber-500/15 px-4 py-3 text-xs font-medium text-amber-200 sm:mx-4"
          >
            {toast}
          </div>
        )}

        <main className="mx-auto w-full min-w-0 max-w-7xl flex-1 p-3 pb-[calc(6.75rem+env(safe-area-inset-bottom))] sm:p-6 sm:pb-[calc(6.75rem+env(safe-area-inset-bottom))] lg:pb-6">
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

          {nav === 'studio' && (
            <MotionStudioView
              jobs={jobs}
              wsConnected={wsConnected}
              onJobUpdated={upsertJob}
              onNotify={notify}
              onOpenQueue={() => setNav('queue')}
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

        <nav
          aria-label="Primary mobile navigation"
          className="fixed inset-x-0 bottom-0 z-40 border-t border-slate-800 bg-[#0d1018]/95 pb-[env(safe-area-inset-bottom)] shadow-[0_-8px_28px_rgba(0,0,0,0.35)] backdrop-blur lg:hidden"
        >
          <div className="mx-auto grid max-w-xl grid-cols-5">
            {MOBILE_NAV_ITEMS.map((item) => {
              const Icon = item.icon;
              const active = nav === item.id;
              return (
                <button
                  key={item.id}
                  type="button"
                  aria-current={active ? 'page' : undefined}
                  onClick={() => setNav(item.id)}
                  className={`relative flex min-h-[4.25rem] min-w-0 flex-col items-center justify-center gap-1 px-1 py-2 text-[10px] font-semibold ${
                    active ? 'text-amber-300' : 'text-slate-400'
                  }`}
                >
                  <Icon className="h-5 w-5 shrink-0" />
                  <span className="max-w-full truncate">{item.label}</span>
                  {item.id === 'queue' && runningCount > 0 && (
                    <span className="absolute right-[16%] top-1.5 min-w-5 rounded-full bg-amber-500 px-1 py-0.5 text-center text-[9px] font-black text-slate-950">
                      {runningCount}
                    </span>
                  )}
                </button>
              );
            })}
            <button
              type="button"
              aria-haspopup="dialog"
              aria-expanded={mobileMenuOpen}
              aria-current={!MOBILE_NAV_ITEMS.some((item) => item.id === nav) ? 'page' : undefined}
              onClick={() => setMobileMenuOpen(true)}
              className={`flex min-h-[4.25rem] min-w-0 flex-col items-center justify-center gap-1 px-1 py-2 text-[10px] font-semibold ${
                MOBILE_NAV_ITEMS.some((item) => item.id === nav) ? 'text-slate-400' : 'text-amber-300'
              }`}
            >
              <Menu className="h-5 w-5 shrink-0" />
              <span>More</span>
            </button>
          </div>
        </nav>
      </div>
    </div>
  );
};
