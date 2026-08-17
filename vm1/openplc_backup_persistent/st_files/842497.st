PROGRAM Main
  VAR
    seed4 : UDINT := 1;
    Switch_Previous : BOOL := FALSE;
    temp_counter : UDINT := 0;
  END_VAR
  VAR
    Substation_Switch AT %QX0.0 : BOOL;
    Backup_Active AT %QX0.1 : BOOL;
    Pipe AT %IX0.0 : BOOL;
    T1_Temp_Alarm AT %IX0.1 : BOOL;
    T1_WindingTemp_C AT %IW1 : INT := 70;
  END_VAR

  (* Backup_Active is a coil written externally by Node-RED's existing *)
  (* health-check/changeover logic, same as your original architecture *)
  (* - the PLC does not set it itself *)

  Pipe := Substation_Switch;

  if Substation_Switch then
      temp_counter := temp_counter + 1;
      if temp_counter >= 100 then
          temp_counter := 0;
          seed4 := seed4 * 89 + 33;
          seed4 := seed4 - (seed4 / 65537) * 65537;
          T1_WindingTemp_C := T1_WindingTemp_C + (UDINT_TO_INT(seed4 - (seed4 / 3) * 3) - 1);
          if T1_WindingTemp_C < 60 then
              T1_WindingTemp_C := 60;
          elsif T1_WindingTemp_C > 95 then
              T1_WindingTemp_C := 95;
          end_if;
      end_if;
  else
      T1_WindingTemp_C := 70;
      temp_counter := 0;
  end_if;

  T1_Temp_Alarm := T1_WindingTemp_C > 90;
  if T1_WindingTemp_C > 95 then
      Substation_Switch := FALSE;
  end_if;

END_PROGRAM


CONFIGURATION Config0

  RESOURCE Res0 ON PLC
    TASK task0(INTERVAL := T#20ms,PRIORITY := 1);
    PROGRAM instance0 WITH task0 : main;
  END_RESOURCE
END_CONFIGURATION
