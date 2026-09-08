package com.deviceagent.harness;
import com.deviceagent.capability.*;
import com.deviceagent.config.DeviceAgentProperties;
import com.deviceagent.domain.*;
import com.deviceagent.policy.PolicyEngine;
import com.deviceagent.device.DeviceException;
import com.deviceagent.device.DevicePort;
import com.deviceagent.simulator.DeviceSimulator;
import com.deviceagent.store.InMemoryRunStore;
import org.springframework.stereotype.Component;
import java.time.Instant;
import java.util.*;

/** Single dispatch point. The run lock protects authorization/reservation, never device waiting. */
@Component
public class CapabilityExecutor {
    private final DevicePort device;
    private final CapabilityRegistry registry;
    private final PolicyEngine policy;
    private final InMemoryRunStore store;
    private final DeviceAgentProperties properties;
    public CapabilityExecutor(DevicePort device,CapabilityRegistry r,PolicyEngine p,InMemoryRunStore st,DeviceAgentProperties props){this.device=device;registry=r;policy=p;store=st;properties=props;}
    public StateSnapshot read(RunRecord r,Set<DeviceDomain> domains){
        r.getBudget().countTool();store.appendEvent(r,"READ_ATTEMPT",Map.of());
        StateSnapshot s=device.readState(domains);
        store.appendEvent(r,"OBSERVE",Ids.dict("state",s.getState(),"revisions",s.getDomainRevisions(),"observed_at",s.getObservedAt()));
        if(!fresh(r,s))throw new DeviceException("STALE_STATE","缺少当前环境的新鲜快照");
        return s;
    }
    public ToolAction executeWrite(RunRecord r,String cap,Map<String,Object> p){return executeWrite(r,cap,p,r.getTask().getGoalVersion(),null);}
    public ToolAction executeWrite(RunRecord r,String cap,Map<String,Object> p,int version,StateSnapshot planned){
        var a=prepare(r,cap,p,version);
        StateSnapshot before=planned;
        if(before==null)before=read(r,EnumSet.allOf(DeviceDomain.class));
        synchronized(r){
            r.getActions().add(a);store.appendEvent(r,"ACTION_PROPOSED",Ids.dict("action_id",a.getActionId(),"capability_id",cap,"params",p,"goal_version",version));
            if(r.isTerminal()||r.isCancelAccepted()||version!=r.getTask().getGoalVersion()||!Objects.equals(r.getEnvironmentId(),device.getEnvironmentId())) return reject(r,a,ExecutionStatus.CANCELLED_BEFORE_DISPATCH,"过期目标、环境或已取消");
            if(r.getInFlightActionId()!=null||r.isUnresolvedUnknown())return reject(r,a,ExecutionStatus.REJECTED,"另有在途或未知动作");
            var decision=policy.decide(r,cap,p);store.appendEvent(r,"POLICY",Ids.dict("action_id",a.getActionId(),"decision",decision.decision(),"message",decision.message()));
            if(decision.decision()==PolicyDecision.DENY)return reject(r,a,ExecutionStatus.REJECTED,decision.message());
            if(!fresh(r,before))return reject(r,a,ExecutionStatus.REJECTED,"状态快照过期");
            if(decision.decision()==PolicyDecision.REQUIRE_CONFIRMATION){
                var pending=new PendingInteraction();pending.setPendingId(Ids.newId("pending"));pending.setType("CONFIRMATION");pending.setGoalVersion(version);pending.setCapabilityId(cap);pending.setParams(new LinkedHashMap<>(p));pending.setExpiresAt(r.getBudget().getDeadline());pending.setQuestion("确认执行 "+cap+" "+p);
                r.setPending(pending);r.setLifecycle(RunLifecycle.WAITING_CONFIRMATION);r.setPhase(RunPhase.WAIT);store.appendEvent(r,"WAIT_CONFIRMATION",pending.toMap());return a;
            }
            a.setExecutionStatus(ExecutionStatus.AUTHORIZED);store.appendEvent(r,"AUTHORIZED",Ids.dict("action_id",a.getActionId()));
            a.setExpectedRevisions(new LinkedHashMap<>(before.getDomainRevisions()));a.setDeadline(r.getBudget().getDeadline());
            r.getBudget().countWrite();r.getBudget().countTool();
            // Stable intent is durably saved by appendEvent BEFORE the DISPATCH reservation.
            store.appendEvent(r,"ACTION_INTENT",Ids.dict("action_id",a.getActionId(),"idempotency_key",a.getIdempotencyKey()));
            a.setExecutionStatus(ExecutionStatus.DISPATCHED);a.setDispatchedAt(Ids.now());r.setInFlightActionId(a.getActionId());
            store.appendEvent(r,"DISPATCH",Ids.dict("action_id",a.getActionId(),"capability_id",cap,"params",p,"goal_version",version));
        }
        try{
            var rec=device.applyWrite(a.getActionId(),a.getIdempotencyKey(),cap,p,a.getEnvironmentId(),a.getDeadline(),a.getExpectedRevisions(),r.getRunId(),version);
            synchronized(r){a.setExecutionStatus(ExecutionStatus.ACKNOWLEDGED);store.appendEvent(r,"ACKNOWLEDGED",Ids.dict("action_id",a.getActionId()));record(r,a,rec);}
        }catch(DeviceException e){synchronized(r){a.setExecutionStatus(ExecutionStatus.UNKNOWN);a.setMessage(e.getCode());r.setUnresolvedUnknown(true);store.appendEvent(r,"TOOL_RESULT",Ids.dict("action_id",a.getActionId(),"execution_status","UNKNOWN","code",e.getCode()));}}
        if(a.getExecutionStatus()==ExecutionStatus.UNKNOWN){
            long end=System.currentTimeMillis()+1000;
            for(int i=0;i<4&&a.getExecutionStatus()==ExecutionStatus.UNKNOWN&&System.currentTimeMillis()<end;i++){
                try{Thread.sleep(60);}catch(InterruptedException e){Thread.currentThread().interrupt();break;}
                reconcileUnknown(r,a);
            }
        }
        verify(r,a);
        synchronized(r){if(a.getExecutionStatus()!=ExecutionStatus.UNKNOWN)r.setInFlightActionId(null);r.setUnresolvedUnknown(a.getExecutionStatus()==ExecutionStatus.UNKNOWN);store.appendEvent(r,"ACTION_SETTLED",Ids.dict("action_id",a.getActionId(),"execution_status",a.getExecutionStatus().name()));}
        return a;
    }
    private ToolAction reject(RunRecord r,ToolAction a,ExecutionStatus status,String reason){a.setExecutionStatus(status);a.setMessage(reason);a.setFinishedAt(Ids.now());store.appendEvent(r,"ACTION_REJECTED",Ids.dict("action_id",a.getActionId(),"execution_status",status.name(),"message",reason));return a;}
    private void record(RunRecord r,ToolAction a,DeviceSimulator.ActionRecord rec){
        a.setExecutionStatus("APPLIED".equals(rec.status)?ExecutionStatus.APPLIED:"NOT_APPLIED".equals(rec.status)?ExecutionStatus.NOT_APPLIED:ExecutionStatus.UNKNOWN);
        a.setMessage(rec.message);a.setFinishedAt(rec.finishedAt);a.getEvidence().put("device_revision",rec.revision);
        if("APPLIED".equals(rec.status)&&Objects.equals(rec.actionId,a.getActionId()))a.setAttribution(Attribution.THIS_ACTION);
        r.setUnresolvedUnknown(a.getExecutionStatus()==ExecutionStatus.UNKNOWN);
        store.appendEvent(r,"TOOL_RESULT",Ids.dict("action_id",a.getActionId(),"execution_status",a.getExecutionStatus().name(),"message",rec.message));
    }
    public void reconcileUnknown(RunRecord r,ToolAction a){
        synchronized(r){if(!r.isTerminal())r.getBudget().countTool();store.appendEvent(r,"RECONCILE_ATTEMPT",Ids.dict("action_id",a.getActionId()));}
        var rec=device.queryAction(a.getActionId());
        synchronized(r){if(rec!=null)record(r,a,rec);store.appendEvent(r,"RECONCILE",Ids.dict("action_id",a.getActionId(),"execution_status",a.getExecutionStatus().name()));}
    }
    private void verify(RunRecord r,ToolAction a){
        synchronized(r){store.appendEvent(r,"VERIFY_ATTEMPT",Ids.dict("action_id",a.getActionId()));}
        try{
            if(!r.isTerminal())r.getBudget().countTool();var s=device.readState(null);
            boolean matches=CapabilityEffects.matches(a.getCapabilityId(),a.getParams(),s.getState());
            a.setVerificationStatus(!fresh(r,s)?VerificationStatus.STALE:matches?VerificationStatus.SATISFIED:VerificationStatus.NOT_SATISFIED);
            // Historical application remains true, but current matching value may have an external origin.
            boolean own=CapabilityEffects.expected(a.getCapabilityId(),a.getParams()).keySet().stream().allMatch(f->Objects.equals(s.getOrigins().getOrDefault(f,Map.of()).get("action_id"),a.getActionId()));
            if(matches&&!own)a.setAttribution(Attribution.EXTERNAL);
            a.getEvidence().put("after_state",s.getState());a.getEvidence().put("origins",s.getOrigins());a.getEvidence().put("revision",s.getRevision());
        }catch(Exception e){a.setVerificationStatus(VerificationStatus.UNAVAILABLE);}
        synchronized(r){store.appendEvent(r,"VERIFY",Ids.dict("action_id",a.getActionId(),"verification_status",a.getVerificationStatus().name(),"attribution",a.getAttribution().name()));}
    }
    private boolean fresh(RunRecord r,StateSnapshot s){return Objects.equals(r.getEnvironmentId(),s.getEnvironmentId())&&s.getObservedAt()!=null&&s.getObservedAt().isAfter(Instant.now().minusMillis(properties.getFreshWindowMs()));}
    private ToolAction prepare(RunRecord r,String cap,Map<String,Object> p,int v){var a=new ToolAction();a.setActionId(Ids.newId("act"));a.setIdempotencyKey(a.getActionId());a.setRunId(r.getRunId());a.setGoalVersion(v);a.setEnvironmentId(r.getEnvironmentId());a.setCapabilityId(cap);a.setParams(p==null?Map.of():new LinkedHashMap<>(p));a.setPreparedAt(Ids.now());a.setExecutionStatus(ExecutionStatus.PROPOSED);return a;}
}
