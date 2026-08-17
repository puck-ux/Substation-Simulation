PROGRAM Main
  VAR
    seed : UDINT := 1;
    seed2 : UDINT := 1;
    seed3 : UDINT := 1;
    seed4 : UDINT := 1;
    Switch_Previous : BOOL := FALSE;
    temp_counter : UDINT := 0;
  END_VAR
  VAR
    Substation_Switch AT %QX0.0 : BOOL;
    Pipe AT %IX0.0 : BOOL;
    Gauge AT %IW1 : INT := 0;
    T1_Temp_Alarm AT %IX0.1 : BOOL;
    Bus1_Voltage_V AT %IW2 : INT := 0;
    FeederCurrent_A AT %IW3 : INT := 0;
    T1_WindingTemp_C AT %IW4 : INT := 70;
    Breaker_OpCount AT %IW5 : INT := 0;
  END_VAR

  Pipe := Substation_Switch;

  if Substation_Switch <> Switch_Previous then
      Breaker_OpCount := Breaker_OpCount + 1;
  end_if;
  Switch_Previous := Substation_Switch;

  if Substation_Switch then
      seed := seed * 75 + 74;
      seed := seed - (seed / 65537) * 65537;
      Gauge := UDINT_TO_INT(seed - (seed / 201) * 201) + 500;

      seed2 := seed2 * 137 + 91;
      seed2 := seed2 - (seed2 / 65537) * 65537;
      Bus1_Voltage_V := UDINT_TO_INT(seed2 - (seed2 / 41) * 41) + 1296;

      seed3 := seed3 * 213 + 51;
      seed3 := seed3 - (seed3 / 65537) * 65537;
      FeederCurrent_A := UDINT_TO_INT(seed3 - (seed3 / 61) * 61) + 250;

      (* winding temp: nudge by -1/0/+1 every ~2s instead of a fresh value every scan *)
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
      Gauge := 0;
      Bus1_Voltage_V := 0;
      FeederCurrent_A := 0;
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
