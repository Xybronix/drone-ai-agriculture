#!/usr/bin/env python3
"""
Script de Verification de Sante - Drone AI Agriculture

Ce script verifie l'etat de tous les composants du systeme et genere un rapport.
"""

import os
import sys
import json
import time
import platform
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from enum import Enum

# Ajouter le repertoire parent au path
sys.path.insert(0, str(Path(__file__).parent.parent))


class Status(Enum):
    OK = "ok"
    WARNING = "warning"
    ERROR = "error"
    UNKNOWN = "unknown"


@dataclass
class CheckResult:
    name: str
    status: Status
    message: str
    details: Optional[Dict[str, Any]] = None
    duration_ms: float = 0


class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    END = '\033[0m'


def get_status_icon(status: Status) -> str:
    icons = {
        Status.OK: f"{Colors.GREEN}[OK]{Colors.END}",
        Status.WARNING: f"{Colors.YELLOW}[WARN]{Colors.END}",
        Status.ERROR: f"{Colors.RED}[ERR]{Colors.END}",
        Status.UNKNOWN: f"{Colors.BLUE}[?]{Colors.END}",
    }
    return icons.get(status, "[?]")


class HealthChecker:
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.results: List[CheckResult] = []
        self.start_time = time.time()

    def add_result(self, result: CheckResult):
        self.results.append(result)
        icon = get_status_icon(result.status)
        print(f"  {icon} {result.name}: {result.message} ({result.duration_ms:.0f}ms)")

    # ========================================================
    # Verifications Systeme
    # ========================================================

    def check_python_version(self):
        start = time.time()
        version = sys.version_info
        version_str = f"{version.major}.{version.minor}.{version.micro}"

        if version.major >= 3 and version.minor >= 8:
            status = Status.OK
            message = f"Python {version_str}"
        elif version.major >= 3:
            status = Status.WARNING
            message = f"Python {version_str} (3.8+ recommande)"
        else:
            status = Status.ERROR
            message = f"Python {version_str} (3.8+ requis)"

        self.add_result(CheckResult(
            name="Python Version",
            status=status,
            message=message,
            details={"version": version_str},
            duration_ms=(time.time() - start) * 1000
        ))

    def check_virtual_environment(self):
        start = time.time()
        venv_path = self.project_root / "venv"

        if venv_path.exists():
            in_venv = sys.prefix != sys.base_prefix
            status = Status.OK if in_venv else Status.WARNING
            message = "Active" if in_venv else "Existant mais non active"
        else:
            status = Status.WARNING
            message = "Non trouve (optionnel)"

        self.add_result(CheckResult(
            name="Environnement Virtuel",
            status=status,
            message=message,
            duration_ms=(time.time() - start) * 1000
        ))

    def check_disk_space(self):
        start = time.time()
        try:
            import shutil
            total, used, free = shutil.disk_usage(self.project_root)
            free_gb = free / (1024**3)
            used_percent = (used / total) * 100

            if free_gb > 10:
                status = Status.OK
                message = f"{free_gb:.1f} GB disponibles ({used_percent:.0f}% utilise)"
            elif free_gb > 2:
                status = Status.WARNING
                message = f"{free_gb:.1f} GB disponibles (attention)"
            else:
                status = Status.ERROR
                message = f"{free_gb:.1f} GB disponibles (critique!)"

            self.add_result(CheckResult(
                name="Espace Disque",
                status=status,
                message=message,
                details={"free_gb": free_gb, "used_percent": used_percent},
                duration_ms=(time.time() - start) * 1000
            ))
        except Exception as e:
            self.add_result(CheckResult(
                name="Espace Disque",
                status=Status.UNKNOWN,
                message=str(e),
                duration_ms=(time.time() - start) * 1000
            ))

    def check_memory(self):
        start = time.time()
        try:
            if platform.system() == "Linux":
                with open("/proc/meminfo", "r") as f:
                    lines = f.readlines()
                    mem_info = {}
                    for line in lines:
                        parts = line.split(":")
                        if len(parts) == 2:
                            key = parts[0].strip()
                            value = int(parts[1].strip().split()[0])
                            mem_info[key] = value

                    total = mem_info.get("MemTotal", 0) / 1024 / 1024
                    available = mem_info.get("MemAvailable", 0) / 1024 / 1024
                    used_percent = ((total - available) / total) * 100 if total > 0 else 0

                    if used_percent < 80:
                        status = Status.OK
                    elif used_percent < 95:
                        status = Status.WARNING
                    else:
                        status = Status.ERROR

                    self.add_result(CheckResult(
                        name="Memoire",
                        status=status,
                        message=f"{available:.1f} GB disponible sur {total:.1f} GB ({used_percent:.0f}% utilise)",
                        details={"total_gb": total, "available_gb": available},
                        duration_ms=(time.time() - start) * 1000
                    ))
            else:
                self.add_result(CheckResult(
                    name="Memoire",
                    status=Status.UNKNOWN,
                    message="Verification non disponible sur ce systeme",
                    duration_ms=(time.time() - start) * 1000
                ))
        except Exception as e:
            self.add_result(CheckResult(
                name="Memoire",
                status=Status.UNKNOWN,
                message=str(e),
                duration_ms=(time.time() - start) * 1000
            ))

    # ========================================================
    # Verifications Fichiers
    # ========================================================

    def check_required_files(self):
        start = time.time()
        required_files = [
            ("requirements.txt", True),
            (".env", True),
            (".env.example", False),
            ("api/__init__.py", True),
            ("api/main.py", True),
            ("api/config.py", True),
            ("api/models.py", True),
            ("api/database.py", True),
            ("api/services/ai_service.py", True),
            ("api/routes/analyze.py", True),
            ("ml/model.py", True),
            ("ml/train_model.py", True),
            ("web/index.html", True),
        ]

        missing_required = []
        missing_optional = []

        for file_path, required in required_files:
            full_path = self.project_root / file_path
            if not full_path.exists():
                if required:
                    missing_required.append(file_path)
                else:
                    missing_optional.append(file_path)

        if not missing_required and not missing_optional:
            status = Status.OK
            message = f"Tous les fichiers presents ({len(required_files)})"
        elif not missing_required:
            status = Status.WARNING
            message = f"Fichiers optionnels manquants: {len(missing_optional)}"
        else:
            status = Status.ERROR
            message = f"Fichiers requis manquants: {', '.join(missing_required[:3])}"

        self.add_result(CheckResult(
            name="Fichiers Requis",
            status=status,
            message=message,
            details={
                "missing_required": missing_required,
                "missing_optional": missing_optional
            },
            duration_ms=(time.time() - start) * 1000
        ))

    def check_directories(self):
        start = time.time()
        required_dirs = [
            "data",
            "logs",
            "models",
            "uploads",
        ]

        missing = []
        for dir_name in required_dirs:
            dir_path = self.project_root / dir_name
            if not dir_path.exists():
                missing.append(dir_name)

        if not missing:
            status = Status.OK
            message = f"Tous les repertoires presents ({len(required_dirs)})"
        else:
            status = Status.WARNING
            message = f"Repertoires manquants: {', '.join(missing)}"

        self.add_result(CheckResult(
            name="Repertoires",
            status=status,
            message=message,
            details={"missing": missing},
            duration_ms=(time.time() - start) * 1000
        ))

    # ========================================================
    # Verifications Dependances
    # ========================================================

    def check_python_dependencies(self):
        start = time.time()
        critical_packages = [
            "fastapi",
            "uvicorn",
            "pydantic",
            "sqlalchemy",
            "aiosqlite",
            "pillow",
            "numpy",
        ]

        installed = []
        missing = []

        for package in critical_packages:
            try:
                __import__(package.replace("-", "_").lower())
                installed.append(package)
            except ImportError:
                try:
                    if package == "pillow":
                        __import__("PIL")
                        installed.append(package)
                    else:
                        missing.append(package)
                except ImportError:
                    missing.append(package)

        if not missing:
            status = Status.OK
            message = f"Toutes les dependances installees ({len(installed)})"
        elif len(missing) <= 2:
            status = Status.WARNING
            message = f"Dependances manquantes: {', '.join(missing)}"
        else:
            status = Status.ERROR
            message = f"Plusieurs dependances manquantes ({len(missing)})"

        self.add_result(CheckResult(
            name="Dependances Python",
            status=status,
            message=message,
            details={"installed": installed, "missing": missing},
            duration_ms=(time.time() - start) * 1000
        ))

    def check_tensorflow(self):
        start = time.time()
        try:
            import tensorflow as tf
            version = tf.__version__

            gpus = tf.config.list_physical_devices('GPU')
            if gpus:
                status = Status.OK
                message = f"TensorFlow {version} avec {len(gpus)} GPU(s)"
            else:
                status = Status.OK
                message = f"TensorFlow {version} (CPU uniquement)"

            self.add_result(CheckResult(
                name="TensorFlow",
                status=status,
                message=message,
                details={"version": version, "gpu_count": len(gpus)},
                duration_ms=(time.time() - start) * 1000
            ))
        except ImportError:
            self.add_result(CheckResult(
                name="TensorFlow",
                status=Status.WARNING,
                message="Non installe (mode simulation sera utilise)",
                duration_ms=(time.time() - start) * 1000
            ))

    # ========================================================
    # Verifications Services
    # ========================================================

    def check_api_health(self, host: str = "localhost", port: int = 8000):
        start = time.time()
        try:
            import urllib.request
            import urllib.error
            url = f"http://{host}:{port}/health"
            with urllib.request.urlopen(url, timeout=5) as response:
                data = json.loads(response.read().decode())
                status = Status.OK
                message = f"API en ligne - {data.get('status', 'ok')}"
                details = data
        except urllib.error.URLError:
            status = Status.WARNING
            message = "API non accessible (non demarree?)"
            details = None
        except Exception as e:
            status = Status.ERROR
            message = f"Erreur: {str(e)}"
            details = None

        self.add_result(CheckResult(
            name="API Health",
            status=status,
            message=message,
            details=details,
            duration_ms=(time.time() - start) * 1000
        ))

    def check_database(self):
        start = time.time()
        db_path = self.project_root / "data" / "agriculture.db"

        if db_path.exists():
            try:
                import sqlite3
                conn = sqlite3.connect(str(db_path))
                cursor = conn.cursor()

                cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
                tables = cursor.fetchall()

                try:
                    cursor.execute("SELECT COUNT(*) FROM analyses")
                    count = cursor.fetchone()[0]
                except sqlite3.OperationalError:
                    count = 0

                conn.close()

                status = Status.OK
                message = f"{len(tables)} tables, {count} analyses"
                details = {"tables": len(tables), "analyses": count}
            except Exception as e:
                status = Status.ERROR
                message = f"Erreur: {str(e)}"
                details = None
        else:
            status = Status.WARNING
            message = "Base de donnees non creee"
            details = None

        self.add_result(CheckResult(
            name="Base de Donnees",
            status=status,
            message=message,
            details=details,
            duration_ms=(time.time() - start) * 1000
        ))

    def check_model(self):
        start = time.time()
        models_dir = self.project_root / "models"

        model_files = []
        if models_dir.exists():
            model_files = list(models_dir.glob("*.h5")) + list(models_dir.glob("*.onnx"))

        if model_files:
            latest = max(model_files, key=lambda p: p.stat().st_mtime)
            size_mb = latest.stat().st_size / (1024 * 1024)
            status = Status.OK
            message = f"Modele trouve: {latest.name} ({size_mb:.1f} MB)"
        else:
            status = Status.WARNING
            message = "Aucun modele trouve (mode simulation)"

        self.add_result(CheckResult(
            name="Modele IA",
            status=status,
            message=message,
            duration_ms=(time.time() - start) * 1000
        ))

    # ========================================================
    # Verifications Docker
    # ========================================================

    def check_docker(self):
        start = time.time()
        try:
            result = subprocess.run(
                ["docker", "version", "--format", "{{.Server.Version}}"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode == 0:
                version = result.stdout.strip()
                status = Status.OK
                message = f"Docker {version} disponible"
            else:
                status = Status.WARNING
                message = "Docker non accessible"
        except FileNotFoundError:
            status = Status.WARNING
            message = "Docker non installe"
        except subprocess.TimeoutExpired:
            status = Status.WARNING
            message = "Docker ne repond pas"

        self.add_result(CheckResult(
            name="Docker",
            status=status,
            message=message,
            duration_ms=(time.time() - start) * 1000
        ))

    def check_docker_containers(self):
        start = time.time()
        try:
            result = subprocess.run(
                ["docker", "compose", "ps", "--format", "json"],
                capture_output=True, text=True, timeout=5,
                cwd=str(self.project_root)
            )
            if result.returncode == 0 and result.stdout.strip():
                containers = []
                for line in result.stdout.strip().split('\n'):
                    if line:
                        try:
                            containers.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass

                running = sum(1 for c in containers if c.get('State') == 'running')
                total = len(containers)

                if running == total and total > 0:
                    status = Status.OK
                    message = f"{running}/{total} conteneurs actifs"
                elif running > 0:
                    status = Status.WARNING
                    message = f"{running}/{total} conteneurs actifs"
                else:
                    status = Status.WARNING
                    message = "Aucun conteneur actif"
            else:
                status = Status.WARNING
                message = "Pas de conteneurs definis"
        except FileNotFoundError:
            status = Status.UNKNOWN
            message = "Docker Compose non disponible"
        except subprocess.TimeoutExpired:
            status = Status.UNKNOWN
            message = "Verification impossible (timeout)"

        self.add_result(CheckResult(
            name="Conteneurs Docker",
            status=status,
            message=message,
            duration_ms=(time.time() - start) * 1000
        ))

    # ========================================================
    # Verifications Reseau
    # ========================================================

    def check_network_connectivity(self):
        start = time.time()
        try:
            import urllib.request
            import urllib.error

            test_urls = [
                ("Google", "https://www.google.com"),
                ("GitHub", "https://github.com"),
            ]

            accessible = []
            for name, url in test_urls:
                try:
                    urllib.request.urlopen(url, timeout=3)
                    accessible.append(name)
                except Exception:
                    pass

            if len(accessible) == len(test_urls):
                status = Status.OK
                message = "Connexion Internet OK"
            elif accessible:
                status = Status.WARNING
                message = f"Connexion partielle: {', '.join(accessible)}"
            else:
                status = Status.ERROR
                message = "Pas de connexion Internet"

            self.add_result(CheckResult(
                name="Reseau",
                status=status,
                message=message,
                details={"accessible": accessible},
                duration_ms=(time.time() - start) * 1000
            ))
        except Exception as e:
            self.add_result(CheckResult(
                name="Reseau",
                status=Status.UNKNOWN,
                message=str(e),
                duration_ms=(time.time() - start) * 1000
            ))

    # ========================================================
    # Execution des verifications
    # ========================================================

    def run_all_checks(self, include_services: bool = True):
        print(f"\n{Colors.CYAN}{Colors.BOLD}=== Verification de Sante - Drone AI Agriculture ==={Colors.END}")
        print(f"{Colors.CYAN}{'='*55}{Colors.END}\n")

        # Systeme
        print(f"{Colors.BLUE}[Systeme]{Colors.END}")
        self.check_python_version()
        self.check_virtual_environment()
        self.check_disk_space()
        self.check_memory()

        # Fichiers
        print(f"\n{Colors.BLUE}[Fichiers]{Colors.END}")
        self.check_required_files()
        self.check_directories()

        # Dependances
        print(f"\n{Colors.BLUE}[Dependances]{Colors.END}")
        self.check_python_dependencies()
        self.check_tensorflow()

        # Services (optionnel)
        if include_services:
            print(f"\n{Colors.BLUE}[Services]{Colors.END}")
            self.check_api_health()
            self.check_database()
            self.check_model()

            print(f"\n{Colors.BLUE}[Docker]{Colors.END}")
            self.check_docker()
            self.check_docker_containers()

            print(f"\n{Colors.BLUE}[Reseau]{Colors.END}")
            self.check_network_connectivity()

        # Resume
        self.print_summary()

    def print_summary(self):
        total_time = (time.time() - self.start_time) * 1000

        ok_count = sum(1 for r in self.results if r.status == Status.OK)
        warning_count = sum(1 for r in self.results if r.status == Status.WARNING)
        error_count = sum(1 for r in self.results if r.status == Status.ERROR)

        print(f"\n{Colors.CYAN}{'='*55}{Colors.END}")
        print(f"{Colors.BOLD}Resume:{Colors.END}")
        print(f"  {Colors.GREEN}OK:{Colors.END} {ok_count}")
        print(f"  {Colors.YELLOW}Warnings:{Colors.END} {warning_count}")
        print(f"  {Colors.RED}Erreurs:{Colors.END} {error_count}")
        print(f"  Temps total: {total_time:.0f}ms")
        print(f"{Colors.CYAN}{'='*55}{Colors.END}\n")

        if error_count > 0:
            print(f"{Colors.RED}Des erreurs ont ete detectees. Consultez les details ci-dessus.{Colors.END}\n")
        elif warning_count > 0:
            print(f"{Colors.YELLOW}Quelques avertissements. Le systeme devrait fonctionner.{Colors.END}\n")
        else:
            print(f"{Colors.GREEN}Tout est en ordre!{Colors.END}\n")

    def export_report(self, output_path: Optional[Path] = None) -> Dict[str, Any]:
        report = {
            "timestamp": datetime.now().isoformat(),
            "project_root": str(self.project_root),
            "summary": {
                "ok": sum(1 for r in self.results if r.status == Status.OK),
                "warnings": sum(1 for r in self.results if r.status == Status.WARNING),
                "errors": sum(1 for r in self.results if r.status == Status.ERROR),
            },
            "checks": [
                {
                    "name": r.name,
                    "status": r.status.value,
                    "message": r.message,
                    "details": r.details,
                    "duration_ms": r.duration_ms
                }
                for r in self.results
            ]
        }

        if output_path:
            output_path.write_text(json.dumps(report, indent=2))
            print(f"Rapport exporte: {output_path}")

        return report


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Verification de sante du systeme")
    parser.add_argument(
        "--no-services",
        action="store_true",
        help="Ne pas verifier les services (API, Docker)"
    )
    parser.add_argument(
        "--export",
        type=str,
        help="Exporter le rapport en JSON"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Afficher le resultat en JSON"
    )

    args = parser.parse_args()

    # Determiner le repertoire du projet
    script_path = Path(__file__).resolve()
    project_root = script_path.parent.parent

    # Executer les verifications
    checker = HealthChecker(project_root)

    if args.json:
        # Mode silencieux pour JSON
        import io
        sys.stdout = io.StringIO()

    checker.run_all_checks(include_services=not args.no_services)

    if args.json:
        sys.stdout = sys.__stdout__
        report = checker.export_report()
        print(json.dumps(report, indent=2))
    elif args.export:
        checker.export_report(Path(args.export))

    # Code de retour base sur les erreurs
    error_count = sum(1 for r in checker.results if r.status == Status.ERROR)
    sys.exit(1 if error_count > 0 else 0)


if __name__ == "__main__":
    main()