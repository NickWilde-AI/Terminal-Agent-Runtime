package com.deviceagent;
import com.deviceagent.capability.*;
import com.deviceagent.simulator.*;
import org.junit.jupiter.api.Test;
import java.time.Instant;
import java.util.Map;
import static org.junit.jupiter.api.Assertions.*;
class SimulatorContractTest {
    DeviceSimulator.ActionRecord write(DeviceSimulator s,String id,String cap,Map<String,Object> p){return s.applyWrite(id,id,cap,p,s.getEnvironmentId(),Instant.now().plusSeconds(5),s.snapshot().getDomainRevisions(),"run",1);}
    @Test void windowsAreIndependentAndAttributed(){var s=new DeviceSimulator();write(s,"a","window.set_position",Map.of("window","front_left","position",50));assertEquals(50,s.snapshot().getState().get("window_front_left"));assertEquals(0,s.snapshot().getState().get("window_front_right"));assertEquals("a",s.snapshot().getOrigins().get("window_front_left").get("action_id"));}
    @Test void ackDoesNotChangeGeometrySource(){var s=new DeviceSimulator();s.injectFault(DeviceSimulator.FaultType.ACK_NOT_APPLIED,"window.set_position",1);var a=write(s,"a","window.set_position",Map.of("window","front_left","position",100));assertEquals("NOT_APPLIED",a.status);assertEquals(0,s.snapshot().getState().get("window_front_left"));}
    @Test void lostResponseKeepsOriginalRecord(){var s=new DeviceSimulator();s.injectFault(DeviceSimulator.FaultType.APPLIED_RESPONSE_LOST,"media.set_volume",1);assertThrows(SimulatorException.class,()->write(s,"a","media.set_volume",Map.of("value",2)));assertEquals("APPLIED",s.queryAction("a").status);long rev=s.snapshot().getRevision();write(s,"a","media.set_volume",Map.of("value",2));assertEquals(rev,s.snapshot().getRevision());}
    @Test void sameKeyDifferentParamsIsRejected(){var s=new DeviceSimulator();write(s,"a","media.set_volume",Map.of("value",2));assertThrows(SimulatorException.class,()->write(s,"a","media.set_volume",Map.of("value",3)));}
    @Test void delayedActionRechecksExternalRevision(){var s=new DeviceSimulator();s.injectFault(DeviceSimulator.FaultType.DELAY_APPLY,"media.set_volume",1);var a=write(s,"a","media.set_volume",Map.of("value",2));s.externalChange("media_volume",9);a.applyAfterMs=1;s.tick();assertEquals("NOT_APPLIED",a.status);assertEquals(9,s.snapshot().getState().get("media_volume"));assertEquals("EXTERNAL",s.snapshot().getOrigins().get("media_volume").get("origin"));}
    @Test void setpointNeverChangesCabinTemperature(){var s=new DeviceSimulator();write(s,"a","climate.set_temperature",Map.of("value",23));assertEquals(27,s.snapshot().getState().get("cabin_temperature"));assertEquals(false,s.snapshot().getState().get("climate_power"));}
    @Test void schemaRejectsUnknownFieldsAndBadValues(){var r=new CapabilityRegistry();assertFalse(r.validate("window.set_position",Map.of("window","all","position",101)).ok());assertFalse(r.validate("media.pause",Map.of("value",true)).ok());assertFalse(r.validate("climate.set_power",Map.of("value","true")).ok());assertFalse(r.validate("climate.set_temperature",Map.of("value",23.5)).ok());}
    @Test void oldEnvironmentCannotApply(){var s=new DeviceSimulator();String env=s.getEnvironmentId();s.forceNewEnvironment();var a=s.applyWrite("a","a","climate.set_power",Map.of("value",true),env,Instant.now().plusSeconds(1),Map.of());assertEquals("NOT_APPLIED",a.status);assertEquals(false,s.snapshot().getState().get("climate_power"));}
}
