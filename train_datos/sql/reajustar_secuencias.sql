-- Tras cargar datos con ids explícitos (simulador), pone cada secuencia
-- de identidad por encima del id máximo para que la app pueda seguir insertando.
DO $$
DECLARE t TEXT;
BEGIN
  FOREACH t IN ARRAY ARRAY['grupo_muscular','musculo','patron_movimiento','ejercicio',
                           'usuario','medida_corporal','programa','programa_ejercicio',
                           'sesion','serie','recomendacion']
  LOOP
    EXECUTE format(
      'SELECT setval(pg_get_serial_sequence(%L, ''id''), COALESCE((SELECT max(id) FROM %I), 0) + 1, false)',
      t, t);
  END LOOP;
END $$;
