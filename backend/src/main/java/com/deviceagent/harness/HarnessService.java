package com.deviceagent.harness;
import com.deviceagent.capability.*;
import com.deviceagent.config.DeviceAgentProperties;
import com.deviceagent.domain.*;
import com.deviceagent.memory.MemoryService;
import com.deviceagent.model.*;
import com.deviceagent.device.DevicePort;
import com.deviceagent.store.*;
import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Service;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.*;

/** One worker per run, version-bound proposals, atomic terminal/control acceptance. */
@Service
public class HarnessService {
    private final InMemoryRunStore store;private final DevicePort device;private final ModelPort model;
    private final TaskBinder binder;private final CapabilityExecutor executor;private final Verifier verifier;
    private final DeviceAgentProperties props;private final SqlitePersistence persistence;private final MemoryService memory;private final ModelRouter router;
    private final ExecutorService workers=Executors.newFixedThreadPool(2,r->{var t=new Thread(r,"harness-worker");t.setDaemon(true);return t;});
    private final ScheduledExecutorService timer=Executors.newSingleThreadScheduledExecutor(r->{var t=new Thread(r,"harness-deadlines");t.setDaemon(true);return t;});
    private final Set<String> running=ConcurrentHashMap.newKeySet();private final Object admission=new Object();
    private volatile boolean evalPause;private final Object barrier=new Object();
    public HarnessService(InMemoryRunStore s,DevicePort device,ModelPort m,TaskBinder b,CapabilityExecutor e,Verifier v,DeviceAgentProperties p,SqlitePersistence db,MemoryService mem,ModelRouter mr){store=s;this.device=device;model=m;binder=b;executor=e;verifier=v;props=p;persistence=db;memory=mem;router=mr;
        timer.scheduleWithFixedDelay(()->{for(var r:store.list())synchronized(r){if(!r.isTerminal()&&r.getBudget().expired())finish(r,RunLifecycle.TIMED_OUT,"TIMED_OUT","任务到期，停止新动作；在途动作仍可能生效",GoalOutcome.UNKNOWN);}},100,100,TimeUnit.MILLISECONDS);
    }
    @PreDestroy void shutdownExecutor(){workers.shutdownNow();timer.shutdownNow();}
    public void armEvalPauseAfterGoalBound(){evalPause=true;}
    public void releaseEvalPause(){synchronized(barrier){evalPause=false;barrier.notifyAll();}}
    private void pause(RunRecord r){if(!evalPause)return;store.appendEvent(r,"EVAL_PAUSE",Map.of("at","GOAL_BOUND"));synchronized(barrier){long end=System.currentTimeMillis()+5000;while(evalPause&&!r.isTerminal()&&System.currentTimeMillis()<end)try{barrier.wait(30);}catch(InterruptedException e){Thread.currentThread().interrupt();break;}}}
    public RunRecord createRun(String id,String text,String session){return createRun(id,text,session,true);}
    public RunRecord createRun(String id,String text,String session,boolean wait){
        if(text==null||text.isBlank()||text.length()>4000)throw new IllegalArgumentException("请输入1至4000字的任务");
        RunRecord r;
        synchronized(admission){
            if(id!=null){var old=store.findByRequestId(id);if(old.isPresent()){r=old.get();if(!Objects.equals(r.getTask().getBindingContext().getOrDefault("original_request",r.getTask().getRawText()),text)||!Objects.equals(r.getSessionId(),session==null?"local":session))throw new IllegalStateException("同 requestId 不同正文");return r;}}
            if(store.hasActiveWriteRun(device.getDeviceId()))throw new IllegalStateException("同设备已有活动任务或未解决 UNKNOWN");
            r=new RunRecord();r.setRunId(Ids.newId("run"));r.setRequestId(id==null?Ids.newId("req"):id);r.setDeviceId(device.getDeviceId());r.setEnvironmentId(device.getEnvironmentId());r.setSessionId(session==null?"local":session);r.getTask().setRunId(r.getRunId());r.getTask().setRawText(text);r.getTask().getBindingContext().put("original_request",text);
            r.getBudget().setDeadline(Instant.now().plusSeconds(props.getBudget().getAbsoluteDeadlineSeconds()));r.getBudget().setMaxModelCalls(props.getBudget().getMaxModelCalls());r.getBudget().setMaxToolCalls(props.getBudget().getMaxToolCalls());r.getBudget().setMaxWriteActions(props.getBudget().getMaxWriteActions());r.getBudget().setMaxReplans(props.getBudget().getMaxReplans());r.getBudget().setMaxSameFailure(props.getBudget().getMaxSameFailure());
            r.getEvaluationSnapshot().put("model_mode",model.mode());r.getEvaluationSnapshot().put("model_id",router.activeModelId());
            store.save(r);store.appendEvent(r,"RUN_RECEIVED",Ids.dict("text",text,"model_mode",model.mode(),"model_id",router.activeModelId()));
        }
        launch(r,wait);return r;
    }
    private void launch(RunRecord r,boolean wait){if(!running.add(r.getRunId()))return;Runnable job=()->{try{work(r);}catch(Exception e){String message=e.getMessage()==null?e.getClass().getSimpleName():e.getMessage();finish(r,RunLifecycle.STOPPED,message.startsWith("BUDGET")?message:"EXECUTION_ERROR","执行停止："+message,GoalOutcome.UNKNOWN);}finally{running.remove(r.getRunId());}};if(wait)job.run();else workers.execute(job);}
    private void work(RunRecord r){
        synchronized(r){if(r.isTerminal())return;r.setLifecycle(RunLifecycle.RUNNING);}
        if(r.getTask().getGoals().isEmpty())compile(r);
        pause(r);
        for(int step=0;step<16;step++){
            int version;long epoch;DeviceTask task;
            synchronized(r){if(r.isTerminal()||r.getLifecycle().name().startsWith("WAITING"))return;version=r.getTask().getGoalVersion();epoch=router.epoch();task=copyTask(r.getTask());}
            if(router.isOfflineEdge()){finish(r,RunLifecycle.STOPPED,"EDGE_UNAVAILABLE","Step Edge UNAVAILABLE：没有本地模型服务，不能继续规划",GoalOutcome.UNKNOWN);return;}
            StateSnapshot s=executor.read(r,EnumSet.allOf(DeviceDomain.class));
            if(externalConflict(r,task,s)){waitFor(r,"CLARIFICATION","设备被外部修改，是否保留外部设置？请修改目标或停止任务");return;}
            Map<String,Object> plan;
            if(r.getRouteType()==RouteType.FAST){plan=TaskBinder.actionFor(task.getGoals().getFirst());if(CapabilityEffects.matches((String)plan.get("capability_id"),TaskBinder.params(plan),s.getState())){conclude(r,version);return;}plan=new LinkedHashMap<>(plan);plan.put("decision","ACT");}
            else{
                synchronized(r){r.setPhase(RunPhase.PLAN);r.getBudget().countModel();store.appendEvent(r,"MODEL_REQUEST",Ids.dict("phase","plan","goal_version",version,"model_epoch",epoch));}
                var prior=prior(r);var ctx=memory.contextBuilder().build(r.getSessionId(),task.getRawText(),task.getGoals(),task.getConstraints(),List.of(),s,prior);
                store.appendEvent(r,"CONTEXT_BUILT",Ids.dict("phase","plan","approx_tokens",ctx.approxTokens(),"memory_ids",ctx.memories().stream().map(x->x.getId()).toList()));
                model.requestContext(r.getRunId(),version,r.getBudget().getDeadline());
                plan=model.planNext(r.getRunId(),task.getGoals(),task.getConstraints(),task.getCriteria().stream().map(c->Ids.dict("template_id",c.getTemplateId(),"params",c.getParams())).toList(),s,prior,ctx.hints());
            }
            synchronized(r){if(stale(r,version,epoch)){store.appendEvent(r,"PLAN_DISCARDED",Ids.dict("planned_version",version,"current_version",r.getTask().getGoalVersion(),"model_epoch",epoch));continue;}store.appendEvent(r,"PLAN",plan);}
            String decision=String.valueOf(plan.get("decision"));
            if("CLARIFY".equals(decision)){waitFor(r,"CLARIFICATION",String.valueOf(plan.getOrDefault("question","请补充目标")));return;}
            if("FINISH".equals(decision)){conclude(r,version);return;}
            if(!"ACT".equals(decision))throw new IllegalArgumentException("非法模型决策");
            String cap=String.valueOf(plan.get("capability_id"));Map<String,Object> params=TaskBinder.params(plan);
            if("device.get_state".equals(cap)||"device.read_state".equals(cap)){model.feedback(r.getRunId(),version,plan,Ids.dict("state",s.getState(),"revision",s.getRevision()));continue;}
            ToolAction a;
            synchronized(r){if(stale(r,version,epoch))continue;r.setPhase(RunPhase.ACT);}
            // Executor rechecks version under the same control lock at the dispatch point.
            a=executor.executeWrite(r,cap,params,version,s);
            model.feedback(r.getRunId(),version,plan,Ids.dict("execution_status",a.getExecutionStatus().name(),"verification_status",a.getVerificationStatus(),"attribution",a.getAttribution(),"action_id",a.getActionId(),"state",a.getEvidence().get("after_state")));
            synchronized(r){if(r.isTerminal()||r.getPending()!=null)return;if(version!=r.getTask().getGoalVersion())continue;}
            if(a.getExecutionStatus()==ExecutionStatus.UNKNOWN){finish(r,RunLifecycle.STOPPED,"UNRESOLVED_ACTION","动作结果未知，已查询原动作；停止新写",GoalOutcome.UNKNOWN);return;}
            if(a.getExecutionStatus()==ExecutionStatus.REJECTED){finish(r,RunLifecycle.STOPPED,"POLICY_DENIED",a.getMessage(),GoalOutcome.UNSATISFIED);return;}
            if(a.getExecutionStatus()==ExecutionStatus.APPLIED){synchronized(r){r.getBudget().resetSameFailure();}}
            if(a.getExecutionStatus()==ExecutionStatus.NOT_APPLIED){
                synchronized(r){r.getBudget().countSameFailure();}
                if(r.getRouteType()==RouteType.AGENT){synchronized(r){r.getBudget().countReplan();}}
            }
            long failures=r.getActions().stream().filter(x->Objects.equals(x.getCapabilityId(),cap)&&Objects.equals(x.getParams(),params)&&x.getExecutionStatus()==ExecutionStatus.NOT_APPLIED).count();
            if(failures>=2||r.getRouteType()==RouteType.FAST){conclude(r,version);return;}
        }
        finish(r,RunLifecycle.STOPPED,"BUDGET_EXHAUSTED_STEP","已达到步骤上限",GoalOutcome.UNKNOWN);
    }
    private void compile(RunRecord r){
        int v;long epoch;String text;
        synchronized(r){v=r.getTask().getGoalVersion();epoch=router.epoch();text=r.getTask().getRawText();r.getBudget().countModel();store.appendEvent(r,"MODEL_REQUEST",Ids.dict("phase","compile","goal_version",v));}
        var snap=executor.read(r,EnumSet.allOf(DeviceDomain.class));var ctx=memory.contextBuilder().buildForCompile(r.getSessionId(),text,snap);
        model.requestContext(r.getRunId(),v,r.getBudget().getDeadline());
        var c=model.compileTask(text,snap,ctx.hints());
        synchronized(r){
            if(stale(r,v,epoch)){store.appendEvent(r,"COMPILE_DISCARDED",Map.of("planned_version",v));return;}
            store.appendEvent(r,"COMPILE",Ids.dict("summary",c.summary,"raw",c.raw));var route=new ExecutionRouter().route(c);r.setRouteType(route);store.appendEvent(r,"ROUTE",Map.of("route",route.name()));
            if(route==RouteType.REJECT){finish(r,RunLifecycle.STOPPED,"UNSUPPORTED",c.rejectReason,GoalOutcome.UNSATISFIED);return;}
            if(route==RouteType.CLARIFY){waitFor(r,"CLARIFICATION",c.clarifyQuestion);return;}
            var task=binder.bind(r.getRunId(),text,props.getDefaultsRuleId(),c);task.setGoalVersion(v);task.getBindingContext().put("original_request",r.getTask().getBindingContext().getOrDefault("original_request",text));task.getBindingContext().put("baseline",snap.getState());task.getBindingContext().put("baseline_revision",snap.getRevision());task.getCriteria().forEach(x->{x.setBoundGoalVersion(v);x.setBaselineObservation(snap.getState());});r.setTask(task);
            store.appendEvent(r,"GOAL_BOUND",Ids.dict("goals",task.getGoals(),"constraints",task.getConstraints(),"goal_version",v));
        }
    }
    private boolean externalConflict(RunRecord r,DeviceTask task,StateSnapshot s){
        long baseline=((Number)task.getBindingContext().getOrDefault("baseline_revision",0L)).longValue();
        for(var c:task.getCriteria())if("field_eq".equals(c.getTemplateId())){String field=String.valueOf(c.getParams().get("field"));var o=s.getOrigins().get(field);if(o!=null&&"EXTERNAL".equals(o.get("origin"))&&((Number)o.get("revision")).longValue()>baseline&&!Verifier.check(c,s)){store.appendEvent(r,"EXTERNAL_CONFLICT",Ids.dict("field",field,"origin",o));return true;}}
        return false;
    }
    private boolean stale(RunRecord r,int v,long epoch){return r.isTerminal()||r.isCancelAccepted()||v!=r.getTask().getGoalVersion()||epoch!=router.epoch();}
    private List<Map<String,Object>> prior(RunRecord r){synchronized(r){return r.getActions().stream().map(a->Ids.dict("capability_id",a.getCapabilityId(),"params",a.getParams(),"execution_status",a.getExecutionStatus().name(),"action_id",a.getActionId(),"goal_version",a.getGoalVersion())).toList();}}
    private void conclude(RunRecord r,int version){
        var result=verifier.verifyTask(r);
        synchronized(r){if(r.isTerminal()||r.getTask().getGoalVersion()!=version)return;r.getEvaluationSnapshot().put("details",result.details());r.getEvaluationSnapshot().put("state",result.snapshot().getState());r.getEvaluationSnapshot().put("revision",result.snapshot().getRevision());
            store.appendEvent(r,"EVALUATE",Ids.dict("outcome",result.outcome().name(),"details",result.details()));boolean partial=result.details().stream().anyMatch(d->"SATISFIED".equals(d.get("status")));
            finish(r,result.outcome()==GoalOutcome.SATISFIED?RunLifecycle.COMPLETED:result.outcome()==GoalOutcome.UNKNOWN?RunLifecycle.STOPPED:partial?RunLifecycle.PARTIAL:RunLifecycle.FAILED,result.outcome()==GoalOutcome.SATISFIED?null:result.outcome().name(),result.summary(),result.outcome());}
    }
    private void finish(RunRecord r,RunLifecycle life,String reason,String summary,GoalOutcome outcome){synchronized(r){if(r.isTerminal())return;r.setLifecycle(life);r.setPhase(RunPhase.FINISH);r.setPending(null);r.setStopReason(reason);r.setResultSummary(summary);r.setGoalOutcome(outcome);r.getEvaluationSnapshot().putIfAbsent("final_state",device.snapshot().getState());store.appendEvent(r,"RUN_FINISHED",Ids.dict("lifecycle",life.name(),"stop_reason",reason,"summary",summary));persistence.persistRun(r);}}
    private void waitFor(RunRecord r,String type,String question){synchronized(r){if(r.isTerminal())return;var p=new PendingInteraction();p.setPendingId(Ids.newId("pending"));p.setGoalVersion(r.getTask().getGoalVersion());p.setType(type);p.setQuestion(question);p.setExpiresAt(r.getBudget().getDeadline());r.setPending(p);r.setLifecycle(RunLifecycle.WAITING_CLARIFICATION);r.setPhase(RunPhase.WAIT);r.setResultSummary(question);store.appendEvent(r,"WAIT_CLARIFICATION",p.toMap());}}
    public RunRecord cancel(String id){var r=get(id);synchronized(r){if(r.isTerminal())return r;r.setCancelAccepted(true);invalidatePending(r);store.appendEvent(r,"CANCEL_ACCEPTED",Ids.dict("in_flight",r.getInFlightActionId()));finish(r,RunLifecycle.CANCELLED,"USER_CANCEL","已取消后续执行；取消前在途动作仍可能生效",GoalOutcome.UNKNOWN);}return r;}
    public RunRecord intervene(String id,String type,String text,Integer expected){return intervene(id,type,text,expected,true);}
    public RunRecord intervene(String id,String type,String text,Integer expected,boolean resume){
        if("CANCEL".equalsIgnoreCase(type)||"停止任务".equals(text)||"取消任务".equals(text))return cancel(id);
        var r=get(id);String t=text==null?"":text;
        synchronized(r){ensureMutable(r,expected);var task=r.getTask();int v=task.getGoalVersion()+1;
            if(task.getGoals().isEmpty())throw new IllegalStateException("仍在理解原目标；可取消，或等待目标出现后修改");
            boolean applied=false;
            if(t.contains("空调先不要")||t.contains("不调空调")||t.contains("空调不要")){task.getGoals().removeIf(g->{var a=TaskBinder.actionFor(g);return a!=null&&String.valueOf(a.get("capability_id")).startsWith("climate.");});task.getConstraints().add(Ids.dict("type","no_cabin_write"));applied=true;}
            if(t.contains("媒体不要")||t.contains("保持外部")){task.getGoals().removeIf(g->{var a=TaskBinder.actionFor(g);return a!=null&&String.valueOf(a.get("capability_id")).startsWith("media.");});task.getConstraints().add(Ids.dict("type","no_media_write"));applied=true;}
            Integer temp=extractInterveneTemperature(t);if(temp!=null){task.getGoals().removeIf(g->{var a=TaskBinder.actionFor(g);return a!=null&&"climate.set_temperature".equals(a.get("capability_id"));});task.getGoals().add(Ids.dict("type","cabin_temperature","value",temp));applied=true;}
            if(t.contains("移除保留导航")||t.contains("不用保留导航")){task.getConstraints().removeIf(c->"keep_navigation_prompt".equals(c.get("type")));applied=true;}
            if(!applied)throw new IllegalArgumentException("修改未被应用：请明确温度、删除空调目标、保留外部媒体设置或取消");
            var c=new CompiledTaskCandidate();c.goals=task.getGoals();c.constraints=task.getConstraints();c.summary=t;
            if(c.goals.isEmpty()&&c.constraints.isEmpty()){task.setGoalVersion(v);finish(r,RunLifecycle.STOPPED,"GOALS_REMOVED","全部目标已移除",GoalOutcome.UNSATISFIED);return r;}
            var updated=binder.bind(r.getRunId(),task.getRawText(),props.getDefaultsRuleId(),c);updated.setGoalVersion(v);updated.getBindingContext().putAll(task.getBindingContext());updated.getCriteria().forEach(x->x.setBoundGoalVersion(v));r.setTask(updated);
            invalidatePending(r);r.setLifecycle(RunLifecycle.RUNNING);r.setRouteType(RouteType.AGENT);store.appendEvent(r,"GOAL_CHANGED",Ids.dict("goal_version",v,"text",t,"goals",updated.getGoals(),"constraints",updated.getConstraints()));
        }
        if(resume)launch(r,false);return r;
    }
    static Integer extractInterveneTemperature(String t){var m=java.util.regex.Pattern.compile("(?:温度|空调)?\\s*(?:改成|设为|调整为|调到)\\s*(\\d{1,2})\\s*度?").matcher(t==null?"":t);if(!m.find())return null;int n=Integer.parseInt(m.group(1));if(n<16||n>30)throw new IllegalArgumentException("有效温度16至30℃");return n;}
    private void ensureMutable(RunRecord r,Integer v){if(r.isTerminal()||r.getBudget().expired())throw new IllegalStateException("任务已结束或到期");if(v!=null&&v!=r.getTask().getGoalVersion())throw new IllegalStateException("goal_version 冲突");}
    private void invalidatePending(RunRecord r){if(r.getPending()!=null)store.appendEvent(r,"PENDING_INVALIDATED",Ids.dict("pending_id",r.getPending().getPendingId()));r.setPending(null);for(var a:r.getActions())if(a.getExecutionStatus()==ExecutionStatus.PROPOSED)a.setExecutionStatus(ExecutionStatus.CANCELLED_BEFORE_DISPATCH);}
    public RunRecord answerClarification(String id,String answer){var r=get(id);synchronized(r){ensureMutable(r,null);if(r.getLifecycle()!=RunLifecycle.WAITING_CLARIFICATION)throw new IllegalStateException("当前不在澄清等待");String text=r.getTask().getRawText()+"；用户补充："+answer;int v=r.getTask().getGoalVersion()+1;var original=r.getTask().getBindingContext().get("original_request");r.setTask(new DeviceTask());r.getTask().setGoalVersion(v);r.getTask().setRawText(text);r.getTask().getBindingContext().put("original_request",original);r.setPending(null);r.setLifecycle(RunLifecycle.RUNNING);store.appendEvent(r,"CLARIFICATION_ANSWER",Map.of("answer",answer));}launch(r,true);return r;}
    public RunRecord answerPending(String id,String pendingId,int v,String decision,String answer){
        var r=get(id);PendingInteraction p;
        synchronized(r){ensureMutable(r,v);p=r.getPending();if(p==null||!p.getPendingId().equals(pendingId)||p.getGoalVersion()!=v||!p.getExpiresAt().isAfter(Ids.now()))throw new IllegalStateException("确认对象已失效");
            if("REJECT".equals(decision)){store.appendEvent(r,"CONFIRM_REJECTED",Map.of("pending_id",pendingId));finish(r,RunLifecycle.STOPPED,"USER_DECLINED","用户拒绝执行",GoalOutcome.UNSATISFIED);return r;}
            if("ANSWER".equals(decision))return answerClarification(id,answer);
            if(!"APPROVE".equals(decision)||!"CONFIRMATION".equals(p.getType()))throw new IllegalArgumentException("无效回答");
            r.setPending(null);r.setLifecycle(RunLifecycle.RUNNING);r.getTask().getBindingContext().put("approved_action",Ids.dict("capability_id",p.getCapabilityId(),"params",p.getParams(),"goal_version",v));store.appendEvent(r,"CONFIRM_APPROVED",Map.of("pending_id",pendingId));
        }
        // Approval is bound to a single capability, parameters and version; no global bypass.
        launch(r,true);return r;
    }
    public Map<String,Object> resetExperiment(){
        List<String> interrupted=new ArrayList<>();
        for(var r:store.list()){
            if(!r.isTerminal()&&Objects.equals(r.getDeviceId(),device.getDeviceId())){
                cancel(r.getRunId());
                interrupted.add(r.getRunId());
            }
        }
        device.forceNewEnvironment();
        device.resetToDefaults();
        return Ids.dict("ok",true,"interrupted_runs",interrupted,"environment_id",device.getEnvironmentId(),"note","实验重置会先取消同设备活动任务，再重建模拟环境");
    }
    private RunRecord get(String id){return store.find(id).orElseThrow(()->new IllegalArgumentException("run not found"));}
    public List<RunRecord> listRuns(){return store.list().stream().sorted(Comparator.comparing(RunRecord::getCreatedAt).reversed()).toList();}
    public Map<String,Object> replay(String id){var r=get(id);return Ids.dict("mode","history_replay","run",toView(r),"events",store.eventsAfter(id,0));}
    public Map<String,Object> toView(RunRecord r){synchronized(r){return Ids.dict("run_id",r.getRunId(),"request_id",r.getRequestId(),"device_id",r.getDeviceId(),"environment_id",r.getEnvironmentId(),"lifecycle",r.getLifecycle().name(),"phase",r.getPhase().name(),"route",r.getRouteType(),"stop_reason",r.getStopReason(),"result_summary",r.getResultSummary(),"goal_outcome",r.getGoalOutcome(),"goal_version",r.getTask().getGoalVersion(),"raw_text",r.getTask().getRawText(),"goals",new ArrayList<>(r.getTask().getGoals()),"constraints",new ArrayList<>(r.getTask().getConstraints()),"criteria",new ArrayList<>(r.getTask().getCriteria()),"pending",r.getPending()==null?null:r.getPending().toMap(),"budget",r.getBudget().toMap(),"actions",new ArrayList<>(r.getActions()),"evaluation_snapshot",new LinkedHashMap<>(r.getEvaluationSnapshot()),"model_mode",r.getEvaluationSnapshot().get("model_mode"),"model_id",r.getEvaluationSnapshot().get("model_id"),"model_placement",router.placement(),"created_at",r.getCreatedAt(),"updated_at",r.getUpdatedAt(),"event_count",r.getEvents().size(),"defaults_rule_id",props.getDefaultsRuleId());}}
    private DeviceTask copyTask(DeviceTask t){var c=new DeviceTask();c.setRawText(t.getRawText());c.setGoalVersion(t.getGoalVersion());c.setGoals(new ArrayList<>(t.getGoals()));c.setConstraints(new ArrayList<>(t.getConstraints()));c.setCriteria(new ArrayList<>(t.getCriteria()));c.setBindingContext(new LinkedHashMap<>(t.getBindingContext()));return c;}
}
