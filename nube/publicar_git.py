#!/usr/bin/env python3
"""Publicar datos generados mediante PR, checks y un despliegue identificable.

No genera contenido ni monta cartas en GAS. Solo se ejecuta en Actions; las pruebas
inyectan un doble de subprocess y nunca llaman a GitHub. Un fallo conserva la rama
y el PR para revisión, sin push a main, rebase automático ni bypass de protecciones.
"""

import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time


SHA = re.compile(r"^[0-9a-f]{40}$")
PATHS = {
    "arranque": ("laminas/", "datos/tiras/", "datos/arranque.json"),
    "mesa": ("laminas/", "datos/tiras/"),
    "relevo": ("datos/manifiesto.json",),
    "maquinas": ("datos/maquinas.json",),
    "chinches": ("datos/encargos.json", "datos/piezas.json", "datos/motores_puntaje.json"),
}
SCRATCH = {"arranque": "arranque.log", "mesa": "mesa.log", "relevo": "relevo.log"}


class PublicationError(RuntimeError):
    pass


def execute(argv, *, cwd, input=None):
    """Nunca imprimir stderr remoto: podría contener datos privados o credenciales."""
    try:
        return subprocess.run(argv, cwd=cwd, input=input, text=True,
                              capture_output=True, timeout=120, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise PublicationError(f"No se pudo completar {argv[0]} {argv[1]}.") from exc


class Publisher:
    def __init__(self, cwd, env=None, runner=execute, clock=time.monotonic,
                 sleep=time.sleep, timeout=900, interval=10):
        self.cwd = Path(cwd)
        self.env = os.environ if env is None else env
        self.runner, self.clock, self.sleep = runner, clock, sleep
        self.timeout, self.interval = timeout, interval
        self.repo = self.env.get("GITHUB_REPOSITORY", "")
        self.run = self.env.get("GITHUB_RUN_ID", "")
        self.attempt = self.env.get("GITHUB_RUN_ATTEMPT", "")
        if (not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", self.repo)
                or not self.run.isdecimal() or not self.attempt.isdecimal()
                or not self.env.get("GH_TOKEN")):
            raise PublicationError("Se requiere el contexto y token de GitHub Actions.")

    def command(self, argv, allowed=(0,), input=None):
        result = self.runner(argv, cwd=self.cwd, input=input)
        if result.returncode not in allowed:
            raise PublicationError(f"Falló {argv[0]} {argv[1]} (salida {result.returncode}).")
        return result.stdout

    def api(self, endpoint, body=None):
        argv = ["gh", "api", "--method", "GET" if body is None else "POST", endpoint]
        if body is not None:
            argv += ["--input", "-"]
        result = self.command(argv, input=None if body is None else json.dumps(body))
        try:
            return json.loads(result) if result.strip() else None
        except ValueError as exc:
            raise PublicationError("GitHub no devolvió JSON válido.") from exc

    def output(self, **values):
        if self.env.get("GITHUB_OUTPUT"):
            with open(self.env["GITHUB_OUTPUT"], "a", encoding="utf-8") as output:
                for key, value in values.items():
                    output.write(f"{key}={value}\n")
        return values

    @staticmethod
    def allowed_path(path, process):
        if ".." in Path(path).parts or "\\" in path or path.startswith("/"):
            return False
        return any(path.startswith(p) if p.endswith("/") else path == p
                   for p in PATHS[process])

    def changed_paths(self, process):
        # Logs y planes ignorados quedan en el mismo runner. Un cambio de código o
        # un conflicto inesperado detiene la publicación; no se borra ni se añade.
        porcelain = self.command(["git", "status", "--porcelain=v1", "--untracked-files=all", "-z"])
        changed = []
        for entry in filter(None, porcelain.split("\0")):
            state, path = entry[:2], entry[3:]
            if state == "??" and path == SCRATCH.get(process):
                continue  # tee conserva diagnóstico local, nunca entra al commit.
            if any(flag in state for flag in "RCU") or not self.allowed_path(path, process):
                raise PublicationError("Hay cambios fuera de las rutas generadas o un conflicto.")
            if (self.cwd / path).is_symlink():
                raise PublicationError("No se publican enlaces simbólicos generados.")
            changed.append(path)
        return changed

    def run_list(self, workflow, branch):
        result = self.api(f"repos/{self.repo}/actions/workflows/{workflow}/runs"
                          f"?event=workflow_dispatch&branch={branch}&per_page=100")
        if not isinstance(result, dict) or not isinstance(result.get("workflow_runs"), list):
            raise PublicationError("No se pudo leer el historial del workflow.")
        if any(not isinstance(run, dict) or not isinstance(run.get("id"), int)
               for run in result["workflow_runs"]):
            raise PublicationError("El historial contiene una corrida inválida.")
        return result["workflow_runs"]

    def dispatch_and_wait(self, workflow, branch, inputs, *, head=None, title=None, deadline=None):
        before = {run["id"] for run in self.run_list(workflow, branch)}
        self.api(f"repos/{self.repo}/actions/workflows/{workflow}/dispatches",
                 {"ref": branch, "inputs": inputs})
        if deadline is None:
            deadline = self.clock() + self.timeout
        while self.clock() < deadline:
            runs = [run for run in self.run_list(workflow, branch)
                    if run.get("id") not in before and run.get("event") == "workflow_dispatch"
                    and run.get("head_branch") == branch
                    and (head is None or run.get("head_sha") == head)
                    and (title is None or run.get("display_title") == title)]
            if len(runs) > 1:
                raise PublicationError("Más de una corrida coincide; se requiere revisión.")
            if runs and runs[0].get("status") == "completed":
                if runs[0].get("conclusion") != "success":
                    raise PublicationError(f"El workflow {workflow} terminó sin éxito.")
                return runs[0]["id"]
            self.sleep(self.interval)
        raise PublicationError(f"Se agotó la espera de la corrida exacta de {workflow}.")

    def required_checks(self, number, deadline):
        # GitHub obliga a aprobar workflows de PR creados con GITHUB_TOKEN.
        # No son pruebas rojas: aún no existen checks de PR aprobados.
        ausentes = 0
        while self.clock() < deadline:
            raw = self.command(["gh", "pr", "checks", str(number), "--repo", self.repo,
                                "--required", "--json", "name,bucket"], allowed=(0, 1, 8))
            # Los PR creados con GITHUB_TOKEN no despiertan checks de pull_request.
            # Tras dispararlos explícitamente, GitHub tarda en asociarlos al head.
            if not raw.strip():
                ausentes += 1
                if ausentes >= 3:
                    return False
                self.sleep(self.interval)
                continue
            try:
                checks = json.loads(raw)
            except ValueError as exc:
                raise PublicationError("GitHub devolvió checks obligatorios inválidos.") from exc
            if not isinstance(checks, list) or any(not isinstance(c, dict) for c in checks):
                raise PublicationError("GitHub devolvió checks obligatorios inválidos.")
            names = {c.get("name") for c in checks}
            if not {"Arquitectura YOD", "verificar"}.issubset(names):
                ausentes += 1
                if ausentes >= 3:
                    return False
                self.sleep(self.interval)
                continue
            if any(c.get("bucket") in ("fail", "cancel", "skipping") for c in checks):
                raise PublicationError("Una comprobación obligatoria no pasó.")
            if all(c.get("bucket") == "pass" for c in checks):
                return True
            self.sleep(self.interval)
        raise PublicationError("Se agotó la espera de los checks obligatorios.")

    def integrate(self, process):
        changed = self.changed_paths(process)
        # Sólo UNA propuesta pendiente por clase; evita desperdiciar créditos y crear
        # decenas de PR idénticos mientras GitHub exige aprobar su CI.
        existentes = self.api(f"repos/{self.repo}/pulls?state=open&per_page=100")
        if not isinstance(existentes, list):
            raise PublicationError("No se pudo comprobar el inventario de PR de Sala.")
        prefijo = f"Sala {process}: archivos generados"
        abiertos = [p for p in existentes if isinstance(p, dict)
                    and str(p.get("title") or "").startswith(prefijo)
                    and (p.get("base") or {}).get("ref") == "main"
                    and p.get("state") == "open"]
        if abiertos:
            numero = max(int(p["number"]) for p in abiertos if isinstance(p.get("number"), int))
            print(f"::notice::Sala {process}: PR #{numero} esperando verificación o revisión. "
                  "No se crea otro ni se monta material no publicado.")
            return self.output(hubo="pendiente", pr=numero)
        if not changed:
            if process == "mesa":
                # Una tira sin cambios puede venir de un merge cuya publicación
                # falló. El montador comprobará/publicará también este commit.
                head = self.command(["git", "rev-parse", "HEAD"]).strip()
                if not SHA.fullmatch(head):
                    raise PublicationError("No se pudo identificar el commit de la mesa.")
                return self.output(hubo="no", merge_sha=head)
            return self.output(hubo="no")
        for path in changed:
            full = self.cwd / path
            if path.endswith(".json") and full.is_file():
                try:
                    json.loads(full.read_text(encoding="utf-8"))
                except (ValueError, UnicodeError) as exc:
                    raise PublicationError("Un archivo JSON generado es inválido.") from exc
        base = self.command(["git", "rev-parse", "HEAD"]).strip()
        if not SHA.fullmatch(base):
            raise PublicationError("No se pudo identificar el commit base.")
        # La revisión viaja con el código aprobado, sin quedar congelada cuando
        # evolucione el atlas. El guard comprobará que existe y admite la propuesta.
        try:
            revision = json.loads((self.cwd / "architecture-impact.json").read_text())["model_revision"]
        except (OSError, ValueError, KeyError) as exc:
            raise PublicationError("No se pudo leer la revisión del atlas aprobada.") from exc
        if not isinstance(revision, str) or not revision.strip():
            raise PublicationError("La revisión del atlas está vacía.")
        impact = {
            "model_revision": revision,
            "proposal_id": "CHG-SALA-PUBLICACION-001",
            "summary": f"Actualizar archivos generados de Sala ({process}), corrida {self.run}, intento {self.attempt}.",
            "components": ["SYS-SALA", "GAS-SALA"],
            "tests": ["python3 nube/verificar.py antes de crear el PR",
                      "JSON válido y rutas generadas permitidas antes del commit",
                      "Arquitectura YOD y todos los checks obligatorios sobre el head exacto"],
            "rollback": "Revertir el commit mediante PR tras revisión; conservar los registros del Sheet y los planes de montaje.",
        }
        (self.cwd / "architecture-impact.json").write_text(
            json.dumps(impact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        branch = f"bot/sala-{process}-{self.run}-{self.attempt}"
        self.command(["git", "checkout", "-b", branch])
        self.command(["git", "add", "--", *changed, "architecture-impact.json"])
        staged = self.command(["git", "diff", "--cached", "--name-only", "-z"]).split("\0")
        if ("architecture-impact.json" not in staged
                or any(p and p != "architecture-impact.json" and not self.allowed_path(p, process)
                       for p in staged)):
            raise PublicationError("El commit incluiría archivos ajenos al proceso.")
        self.command(["git", "diff", "--cached", "--check"])
        self.command(["git", "-c", "user.name=github-actions[bot]", "-c",
                      "user.email=41898282+github-actions[bot]@users.noreply.github.com",
                      "commit", "-m", f"Sala {process}: actualizar datos mediante PR"])
        head = self.command(["git", "rev-parse", "HEAD"]).strip()
        if not SHA.fullmatch(head) or head == base:
            raise PublicationError("No se generó un commit nuevo válido.")
        self.command(["git", "push", "--set-upstream", "origin", branch])
        pr = None
        try:
            pr = self.api(f"repos/{self.repo}/pulls", {
                "title": f"Sala {process}: archivos generados (corrida {self.run})",
                "head": branch, "base": "main",
                "body": "Actualización automática de rutas generadas.\n\n"
                        "Propuesta: CHG-SALA-PUBLICACION-001. Requiere Arquitectura YOD y "
                        "los checks obligatorios sobre el commit exacto. El montaje espera "
                        "la publicación verificada. Rollback mediante PR; conservar registros del Sheet.",
            })
            if not isinstance(pr, dict) or not isinstance(pr.get("number"), int):
                raise PublicationError("GitHub no devolvió un PR válido.")
            number = pr["number"]
            print(f"PR #{number}: esperando validaciones del commit generado.")
            deadline = self.clock() + self.timeout
            self.dispatch_and_wait("arquitectura.yml", branch,
                                   {"base_sha": base, "head_sha": head}, head=head, deadline=deadline)
            # En un PR creado por github-actions[bot], pull_request no activa verificar.yml.
            # workflow_dispatch sí produce su propio check sobre el SHA exacto.
            self.dispatch_and_wait("verificar.yml", branch, {}, head=head, deadline=deadline)
            if not self.required_checks(number, deadline):
                print(f"::notice::PR #{number} necesita aprobación de los checks de "
                      "pull_request; queda pendiente sin marcar fallo de producción.")
                return self.output(hubo="pendiente", pr=number)
            current = self.api(f"repos/{self.repo}/pulls/{number}")
            if (not isinstance(current, dict) or current.get("state") != "open" or current.get("draft")
                    or not isinstance(current.get("head"), dict)
                    or not isinstance(current.get("base"), dict)
                    or current.get("head", {}).get("sha") != head
                    or current.get("base", {}).get("ref") != "main"):
                raise PublicationError("El PR cambió después de validar su commit.")
            if current.get("mergeable_state") == "blocked":
                print(f"::notice::PR #{number}: GitHub exige un check de pull_request "
                      "o una revisión. Se conserva el PR sin intentar saltar protecciones.")
                return self.output(hubo="pendiente", pr=number)
            self.command(["gh", "pr", "merge", str(number), "--repo", self.repo,
                          "--squash", "--match-head-commit", head])
            merged = self.api(f"repos/{self.repo}/pulls/{number}")
            if not isinstance(merged, dict):
                raise PublicationError("GitHub no confirmó el estado de la integración.")
            sha = merged.get("merge_commit_sha", "")
            if not merged.get("merged") or not isinstance(sha, str) or not SHA.fullmatch(sha):
                raise PublicationError("GitHub no confirmó la integración; revisar cola o protecciones.")
            return self.output(hubo="si", merge_sha=sha, pr=number)
        except PublicationError as exc:
            number = pr.get("number") if isinstance(pr, dict) else None
            recovery = f" Revisar PR #{number}." if number else " Revisar la rama de esta corrida."
            raise PublicationError(str(exc) + recovery + " No montar cartas.") from exc

    def publish(self, sha, process):
        if not SHA.fullmatch(sha):
            raise PublicationError("La publicación requiere el SHA completo de la integración.")
        publication_id = f"{process}-{self.run}-{self.attempt}"
        # El ref es una rama admitida por workflow_dispatch; el workflow valida y
        # hace checkout del input SHA, aunque main avance mientras se espera.
        title = f"Sala publicar · {sha} · {publication_id}"
        run_id = self.dispatch_and_wait("publicar.yml", "main",
                                       {"sha": sha, "publicacion_id": publication_id}, title=title)
        return self.output(publicado_sha=sha, publicacion_run=run_id)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("integrar", "publicar"))
    parser.add_argument("--proceso", required=True, choices=tuple(PATHS))
    parser.add_argument("--sha", default="")
    args = parser.parse_args()
    try:
        publisher = Publisher(Path(__file__).resolve().parent.parent)
        if args.action == "integrar":
            publisher.integrate(args.proceso)
        else:
            publisher.publish(args.sha, args.proceso)
    except PublicationError as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
