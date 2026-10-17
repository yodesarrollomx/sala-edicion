function comprobarHistoricoSala20261017() {
  var r = leerProduccionHistorica_();
  if (!r || r.ok !== true || r.contrato !== 'produccion-historica-v1' ||
      r.version !== 'produccion-historica-2026-10-15' || r.alcance !== 'historial_completo' ||
      !Array.isArray(r.propuestas) || !r.fuentes || r.fuentes.activas !== r.propuestas.length) {
    throw new Error('Contrato histórico sin confirmar');
  }
  var resumen = {ok:true, contrato:r.contrato, version:r.version, alcance:r.alcance,
    propuestas:r.propuestas.length, fuentes:r.fuentes};
  console.log(JSON.stringify(resumen));
  return resumen;
}
