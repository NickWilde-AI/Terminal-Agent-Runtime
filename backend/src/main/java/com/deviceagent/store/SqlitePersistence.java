package com.deviceagent.store;
import com.deviceagent.config.DeviceAgentProperties;
import com.deviceagent.domain.*;
import com.deviceagent.simulator.DeviceSimulator;
import com.fasterxml.jackson.databind.*;
import jakarta.annotation.PostConstruct;
import org.springframework.stereotype.Component;
import java.nio.file.*;
import java.sql.*;
import java.util.*;
/** Independent V2 run journal and device transaction; recovery performs no new device commands. */
@Component
public class SqlitePersistence {
    private final DeviceAgentProperties props;private final InMemoryRunStore store;private final DeviceSimulator simulator;private final ObjectMapper mapper;private final Path path;
    public SqlitePersistence(DeviceAgentProperties p,InMemoryRunStore s,DeviceSimulator sim,ObjectMapper m){props=p;store=s;simulator=sim;mapper=m.copy().disable(DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES);path=Path.of(p.getSqlitePath());}
    private boolean enabled(){return "sqlite".equals(props.getPersistence());}
    @PostConstruct public void init()throws Exception{
        if(!enabled())return;
        Files.createDirectories(path.toAbsolutePath().getParent());
        try(var c=conn();var s=c.createStatement()){s.execute("create table if not exists v2_runs(id text primary key,payload text not null)");s.execute("create table if not exists v2_device(id integer primary key,payload text not null)");}
        try(var c=conn();var s=c.createStatement();var rows=s.executeQuery("select payload from v2_device where id=1")){if(rows.next())simulator.restore(mapper.readValue(rows.getString(1),Map.class),mapper);}
        simulator.terminateQueuedActions();
        // Restore while device callbacks are disabled, then install commit sinks.
        var recovered=new ArrayList<RunRecord>();
        try(var c=conn();var s=c.createStatement();var rows=s.executeQuery("select payload from v2_runs")){while(rows.next())recovered.add(mapper.readValue(rows.getString(1),RunRecord.class));}
        store.onPersist(this::persistRun);simulator.onPersist(this::persistDevice);persistDevice(simulator.exportState());
        for(var r:recovered){
            store.save(r);boolean interrupted=!r.isTerminal();
            if(interrupted){r.setLifecycle(RunLifecycle.INTERRUPTED);r.setPhase(RunPhase.FINISH);r.setPending(null);r.setStopReason("PROCESS_RESTART");r.setResultSummary("进程重启中断；旧确认失效，仅只读对账，不自动续跑");}
            if(interrupted||r.isUnresolvedUnknown()){
                int reads=0;boolean unknown=false;
                for(var a:r.getActions()){
                    if(a.getExecutionStatus()==ExecutionStatus.PROPOSED||a.getExecutionStatus()==ExecutionStatus.AUTHORIZED){a.setExecutionStatus(ExecutionStatus.CANCELLED_BEFORE_DISPATCH);continue;}
                    if(a.getExecutionStatus()!=ExecutionStatus.DISPATCHED&&a.getExecutionStatus()!=ExecutionStatus.UNKNOWN&&a.getExecutionStatus()!=ExecutionStatus.ACKNOWLEDGED)continue;
                    var rec=reads++<4?simulator.queryAction(a.getActionId()):null;
                    if(rec==null){a.setExecutionStatus(ExecutionStatus.UNKNOWN);unknown=true;}
                    else {a.setExecutionStatus("APPLIED".equals(rec.status)?ExecutionStatus.APPLIED:ExecutionStatus.NOT_APPLIED);a.setAttribution("APPLIED".equals(rec.status)?Attribution.THIS_ACTION:Attribution.UNKNOWN);a.getEvidence().put("recovery_device_record",rec);}
                    store.appendEvent(r,"RECOVERY_READ",Ids.dict("action_id",a.getActionId(),"status",a.getExecutionStatus().name(),"origin","RECOVERY"));
                }
                r.setUnresolvedUnknown(unknown);if(!unknown)r.setInFlightActionId(null);
                store.appendEvent(r,"RECOVERED_READ_ONLY",Ids.dict("interrupted",interrupted,"unresolved",unknown,"reads",Math.min(reads,4)));
            }
            persistRun(r);
        }
    }
    public void persistRun(RunRecord r){if(!enabled())return;synchronized(r){save("v2_runs",r.getRunId(),r);}}
    private void persistDevice(Map<String,Object> data){if(enabled())save("v2_device",1,data);}
    private void save(String table,Object id,Object data){
        try(var c=conn();var ps=c.prepareStatement("insert into "+table+"(id,payload) values(?,?) on conflict(id) do update set payload=excluded.payload")){ps.setObject(1,id);ps.setString(2,mapper.writeValueAsString(data));ps.executeUpdate();}catch(Exception e){throw new IllegalStateException("SQLITE_STORAGE_UNAVAILABLE",e);}
    }
    public List<Map<String,Object>> listInterruptedSnapshots(){return store.list().stream().filter(r->r.getLifecycle()==RunLifecycle.INTERRUPTED).map(r->Ids.dict("run_id",r.getRunId(),"lifecycle","INTERRUPTED")).toList();}
    private Connection conn()throws SQLException{var c=DriverManager.getConnection("jdbc:sqlite:"+path.toAbsolutePath());try(var s=c.createStatement()){s.execute("PRAGMA busy_timeout=5000");s.execute("PRAGMA synchronous=FULL");}return c;}
}
