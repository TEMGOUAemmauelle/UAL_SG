import time
import psutil
import threading
import os
import subprocess
import re
try:
    import pynvml
    HAS_PYNVML = True
except ImportError:
    HAS_PYNVML = False

class ResourceMonitor:
    """
    Monitore les ressources système (CPU, RAM, GPU) pendant l'exécution d'une tâche
    et capture la consommation énergétique réelle via 'perf' (Option Pro).
    """
    
    def __init__(self, interval=0.1):
        self.interval = interval
        self.stop_event = threading.Event()
        self.thread = None
        self.cpu_usages = []
        self.memory_usages = []
        self.gpu_usages = []
        self.vram_usages = []
        self.gpu_power_usages = []
        self.start_time = 0
        self.end_time = 0
        
        # Perf Metrics
        self.perf_process = None
        self.real_energy_joules = 0.0
        
        # Initialisation NVML pour GPU NVIDIA
        self.has_gpu = False
        if HAS_PYNVML:
            try:
                pynvml.nvmlInit()
                self.has_gpu = True
                self.gpu_handle = pynvml.nvmlDeviceGetHandleByIndex(0)
            except pynvml.NVMLError as e:
                print(f"  [!] GPU Détecté mais NVML Error : {e}")
                print(f"      (Vérifiez que les pilotes NVIDIA sont installés et nvidia-smi fonctionne)")
                self.has_gpu = False
            except Exception:
                self.has_gpu = False

    def start(self):
        """Démarre le monitoring en arrière-plan et lance 'perf'."""
        self.stop_event.clear()
        self.cpu_usages = []
        self.memory_usages = []
        self.gpu_usages = []
        self.vram_usages = []
        self.real_energy_joules = 0.0
        
        # Lancer Perf en mode système (-a) car RAPL est global
        try:
            # -x, : CSV output format
            # -a  : system-wide
            self.perf_process = subprocess.Popen(
                ["perf", "stat", "-x,", "-a", "-e", "power/energy-pkg/", "sleep", "infinity"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                preexec_fn=os.setsid
            )
        except Exception as e:
            print(f"  [!] Erreur lancement 'perf' : {e}")
            self.perf_process = None

        self.start_time = time.time()
        self.thread = threading.Thread(target=self._monitor_loop)
        self.thread.start()

    def stop(self):
        """Arrête le monitoring et récupère les données de 'perf'."""
        self.stop_event.set()
        if self.thread:
            self.thread.join()
        
        if self.perf_process:
            try:
                # Envoyer SIGINT au groupe de processus (perf + sleep)
                os.killpg(os.getpgid(self.perf_process.pid), subprocess.signal.SIGINT)
                _, stderr = self.perf_process.communicate(timeout=2)
                self.real_energy_joules = self._parse_perf_energy(stderr)
                if self.real_energy_joules == 0:
                    self.real_energy_joules = self._parse_perf_energy_fallback(stderr)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(self.perf_process.pid), subprocess.signal.SIGKILL)
                except Exception:
                    self.perf_process.kill()
                try:
                    _, stderr = self.perf_process.communicate(timeout=2)
                    self.real_energy_joules = self._parse_perf_energy(stderr)
                except Exception:
                    pass
            except Exception as e:
                print(f"  [!] Erreur lors de l'arrêt de 'perf' : {e}")
            
        self.end_time = time.time()
        return self.get_stats()

    def _parse_perf_energy(self, output):
        """Parse le format CSV de perf : 'valeur,,event,...'"""
        total = 0.0
        found = False
        for line in output.split('\n'):
            if "power/energy-pkg/" in line:
                parts = line.split(',')
                if parts and parts[0]:
                    val = self._clean_number(parts[0])
                    if val > 0:
                        total += val
                        found = True
        return total if found else 0.0

    def _parse_perf_energy_fallback(self, output):
        """Fallback sur le format texte si le CSV échoue."""
        match = re.search(r"([\d,.\s]+)\s+Joules", output)
        if match:
            return self._clean_number(match.group(1))
        return 0.0

    def _clean_number(self, num_str):
        """Nettoie un nombre (gestion des milliers et virgules décimales)."""
        try:
            # Supprimer les espaces
            s = num_str.strip().replace(' ', '')
            if not s: return 0.0
            
            # Détection du séparateur décimal (le dernier . ou ,)
            last_dot = s.rfind('.')
            last_comma = s.rfind(',')
            
            if last_comma > last_dot:
                # Format européen : 1.250,45 -> on enlève le . et on remplace , par .
                s = s.replace('.', '').replace(',', '.')
            elif last_dot > last_comma:
                # Format anglais : 1,250.45 -> on enlève la ,
                s = s.replace(',', '')
                
            return float(s)
        except:
            return 0.0

    def _monitor_loop(self):
        # On monitore le CPU système global
        # Optimisation : on cherche les PIDs d'ollama une seule fois ou périodiquement
        ollama_pids = []
        last_pid_check = 0
        
        while not self.stop_event.is_set():
            cpu = psutil.cpu_percent(interval=None) 
            self.cpu_usages.append(cpu)
            
            # Mise à jour des PIDs toutes les 2 secondes
            if time.time() - last_pid_check > 2:
                ollama_pids = [p.info['pid'] for p in psutil.process_iter(['name', 'pid']) 
                               if 'ollama' in p.info['name'].lower()]
                last_pid_check = time.time()
            
            ram_mb = 0
            try:
                for pid in ollama_pids:
                    if psutil.pid_exists(pid):
                        ram_mb += psutil.Process(pid).memory_info().rss / (1024 * 1024)
            except:
                pass
            
            # Fallback
            if ram_mb == 0:
                try: ram_mb = psutil.Process(os.getpid()).memory_info().rss / (1024 * 1024)
                except: pass
                
            self.memory_usages.append(ram_mb)

            if self.has_gpu:
                try:
                    util = pynvml.nvmlDeviceGetUtilizationRates(self.gpu_handle)
                    mem_info = pynvml.nvmlDeviceGetMemoryInfo(self.gpu_handle)
                    power_mw = pynvml.nvmlDeviceGetPowerUsage(self.gpu_handle)
                    
                    self.gpu_usages.append(util.gpu)
                    self.vram_usages.append(mem_info.used / (1024 * 1024))
                    self.gpu_power_usages.append(power_mw)
                except:
                    pass
            
            time.sleep(self.interval)

    def get_stats(self):
        duration = self.end_time - self.start_time
        avg_cpu = sum(self.cpu_usages) / len(self.cpu_usages) if self.cpu_usages else 0.0
        max_ram = max(self.memory_usages) if self.memory_usages else 0.0
        avg_gpu = sum(self.gpu_usages) / len(self.gpu_usages) if self.gpu_usages else 0.0
        max_vram = max(self.vram_usages) if self.vram_usages else 0.0
        
        avg_cpu = sum(self.cpu_usages) / len(self.cpu_usages) if self.cpu_usages else 0.0
        
        # 1. Énergie CPU : Réelle (perf) ou Estimation
        if self.real_energy_joules > 0:
            cpu_energy = self.real_energy_joules
            source_parts = ["perf (RAPL)"]
        else:
            # Fallback CPU estimation (15W idle + 30W load)
            watts_cpu = 15.0 + (30.0 * (avg_cpu / 100.0))
            cpu_energy = watts_cpu * duration
            source_parts = ["estimation"]

        # 2. Énergie GPU (si disponible) : mW * sec / 1000
        gpu_energy = 0.0
        if self.has_gpu and self.gpu_power_usages:
            avg_gpu_power_mw = sum(self.gpu_power_usages) / len(self.gpu_power_usages)
            gpu_energy = (avg_gpu_power_mw / 1000.0) * duration
            source_parts.append("GPU (NVML)")

        total_joules = cpu_energy + gpu_energy
        
        stats = {
            "duree_sec": round(duration, 2),
            "cpu_avg_percent": round(avg_cpu, 1),
            "ram_max_mb": round(max_ram, 1),
            "energy_joules": round(total_joules, 2),
            "energy_source": " + ".join(source_parts)
        }

        if self.has_gpu:
            stats["gpu_util_avg"] = round(avg_gpu, 1)
            stats["vram_max_mb"] = round(max_vram, 1)
            
        return stats
