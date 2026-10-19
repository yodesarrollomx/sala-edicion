---
name: yod-contexto-eficiente
description: Jev primero, lectura selectiva, cambios mínimos y pruebas verificables en YOD OS.
---
# Procedimiento YOD OS para agentes
1. Respetar AGENTS.md y CLAUDE.md y las reglas de producción de Sala de Edición.
2. Ante búsquedas en fuentes conectadas ejecutar jev_triage, y skill jev-ahorro-tokens si está disponible; de otro modo informar ausencia. Buscar fragmentos y aplicar jev_filtrar_pasajes antes de leer íntegramente. En alta confianza >=0.95 usar pasajes adecuados; en decisiones sensibles, contradicciones o dudas revisar fuentes completas.
3. Ubicar componente, atlas, dependencias y estado real. Usar Graphify solamente si está instalado y actualizado. No inventar un índice.
4. Plan -> Build -> Test -> Review -> Ship; limitar cambios y conservar controles de seguridad, pruebas y reversión.
5. Marcar propuesto / implementado / probado / desplegado por separado. Registrar commit, pruebas, evidencia, bloqueo y responsable.
6. Ponytail y Agent Skills externos son optativos; OmniRoute no se activa para datos privados sin autorización explícita.
