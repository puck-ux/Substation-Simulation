PROGRAM Main
  VAR
    seed : UDINT := 1;
  END_VAR
  VAR
    Substation_Switch AT %QX0.0 : BOOL;
    Pipe AT %IX0.0 : BOOL;
    Gauge AT %IW1 : INT := 0;
  END_VAR

  Pipe := Substation_Switch;

  if Substation_Switch then
      seed := seed * 75 + 74;
      seed := seed - (seed / 65537) * 65537;
      Gauge := UDINT_TO_INT(seed - (seed / 201) * 201) + 500;
  else
      Gauge := 0;
  end_if;
END_PROGRAM


CONFIGURATION Config0

  RESOURCE Res0 ON PLC
    TASK task0(INTERVAL := T#20ms,PRIORITY := 1);
    PROGRAM instance0 WITH task0 : main;
  END_RESOURCE
END_CONFIGURATION
