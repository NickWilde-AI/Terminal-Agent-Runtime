package com.deviceagent.simulator;

import com.deviceagent.capability.*;
import com.deviceagent.domain.*;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.function.Consumer;

/** Device state and action records have no access to user text, goals or scoring data. */
public class DeviceSimulator implements com.deviceagent.device.DevicePort {
    public enum FaultType { NONE, REJECT, ACK_NOT_APPLIED, APPLIED_RESPONSE_LOST, DELAY_APPLY, TOOL_TIMEOUT, READ_FAIL, STALE_STATE }
    public static class ActionRecord {
        public String actionId,idempotencyKey,capabilityId,environmentId,runId,status,message;
        public int goalVersion;
        public Map<String,Object> params=new LinkedHashMap<>();
        public Map<String,Long> expectedRevisions=new LinkedHashMap<>();
        public Instant createdAt,finishedAt,deadline;
        public long applyAfterMs,revision;
    }
    private final CapabilityRegistry registry=new CapabilityRegistry();
    private final Map<String,Object> state=new LinkedHashMap<>();
    private final Map<String,Long> revisions=new LinkedHashMap<>();
    private final Map<String,Map<String,Object>> origins=new LinkedHashMap<>();
    private final Map<String,ActionRecord> actionsById=new LinkedHashMap<>(),actionsByKey=new LinkedHashMap<>();
    private String environmentId=Ids.newId("env");
    private long revision=1;
    private FaultType fault=FaultType.NONE;
    private String faultCapability;
    private int remaining;
    private Consumer<Map<String,Object>> persistence=s -> {};
    private final CopyOnWriteArrayList<Consumer<Map<String,Object>>> changeListeners=new CopyOnWriteArrayList<>();
    public DeviceSimulator(){ defaults(); }
    public String getDeviceId(){return "demo-cabin-1";}
    public synchronized String getEnvironmentId(){return environmentId;}
    public synchronized void onPersist(Consumer<Map<String,Object>> sink){persistence=sink;}
    /** @deprecated prefer {@link #addChangeListener(Consumer)} for multi-subscriber SSE */
    public synchronized void onChange(Consumer<Map<String,Object>> sink){addChangeListener(sink);}
    public void addChangeListener(Consumer<Map<String,Object>> sink){changeListeners.add(sink);}
    public void removeChangeListener(Consumer<Map<String,Object>> sink){changeListeners.remove(sink);}
    private void defaults(){
        state.clear(); state.putAll(Ids.dict("climate_power",false,"temperature_setpoint",26,"cabin_temperature",27,"fan_level",3,
          "window_open",false,"media_volume",8,"media_muted",false,"media_playing",false,"media_track",null,"media_artist",null,
          "navigation_active",true,"navigation_destination",null,"navigation_paused",false,
          "navigation_waypoints",new ArrayList<String>(),"navigation_preference","fastest",
          "navigation_home","虹桥幸福里","navigation_company","陆家嘴办公楼",
          "navigation_eta_minutes",null,"last_nav_query_type",null,"last_nav_query_result",null,
          "route_points",List.of(),"prompt_enabled",true,"navigation_volume",5,"navigation_muted",false,
          "route_available",true,"focus_available",true,"last_prompt_event_id",null,"last_prompt_at",null,"last_prompt_result",null,"last_prompt_navigation_revision",0L,
          "life_session_active",false,"life_phase","idle","life_last_keyword",null,"life_last_shop",null,"life_last_item",null));
        CapabilityRegistry.WINDOWS.forEach(w -> state.put("window_"+w,0));
        for(var d:DeviceDomain.values()) revisions.put(d.name(),1L);
        origins.clear(); revision=1;
    }
    public synchronized void resetToDefaults(){
        if(actionsById.values().stream().anyMatch(a -> "QUEUED".equals(a.status))) throw new SimulatorException("RESET_BUSY","存在在途动作");
        defaults(); actionsById.clear(); actionsByKey.clear(); clearFault(); environmentId=Ids.newId("env"); commit();
    }
    public synchronized void forceNewEnvironment(){
        actionsById.clear();actionsByKey.clear();clearFault();environmentId=Ids.newId("env");revision++;commit();
    }
    public synchronized void injectFault(FaultType type,String cap,int times){
        if(times<1 || times>1000) throw new IllegalArgumentException("times must be 1..1000");
        fault=type;faultCapability=cap;remaining=times;
    }
    public synchronized void clearFault(){fault=FaultType.NONE;remaining=0;}
    private boolean consume(FaultType type,String cap){
        if(fault!=type || remaining<=0) return false;
        if(faultCapability!=null && !sameCapability(faultCapability, cap)) return false;
        remaining--;return true;
    }
    private boolean sameCapability(String a,String b){
        if(Objects.equals(a,b)) return true;
        String ca=canonical(a), cb=canonical(b);
        return Objects.equals(ca,cb);
    }
    private String canonical(String id){
        return registry.get(id).map(CapabilityDefinition::getId).orElse(id);
    }
    public synchronized StateSnapshot readState(Set<DeviceDomain> domains){
        if(consume(FaultType.READ_FAIL,null)) throw new SimulatorException("READ_UNAVAILABLE","状态读取不可用");
        StateSnapshot snap=snapshot();
        if(consume(FaultType.STALE_STATE,null)) snap.setObservedAt(Instant.now().minusSeconds(30));
        return snap;
    }
    /** Display/persistence observation does not consume an Agent's injected read fault. */
    public synchronized StateSnapshot snapshot(){
        var s=new StateSnapshot();s.setDeviceId(getDeviceId());s.setEnvironmentId(environmentId);s.setObservedAt(Ids.now());
        s.setState(new LinkedHashMap<>(state));s.setDomainRevisions(new LinkedHashMap<>(revisions));s.setRevision(revision);
        s.setOrigins(new LinkedHashMap<>(origins));return s;
    }
    public synchronized ActionRecord applyWrite(String id,String key,String cap,Map<String,Object> p,String env,Instant deadline,Map<String,Long> revs){
        return applyWrite(id,key,cap,p,env,deadline,revs,null,0);
    }
    public synchronized ActionRecord applyWrite(String id,String key,String cap,Map<String,Object> p,String env,Instant deadline,Map<String,Long> revs,String runId,int goalVersion){
        var old=actionsByKey.get(key);
        if(old!=null){
            if(!Objects.equals(old.params,p)||!Objects.equals(old.capabilityId,cap)||!Objects.equals(old.environmentId,env)) throw new SimulatorException("IDEMPOTENCY_CONFLICT","同键参数或环境不一致");
            return old;
        }
        var a=new ActionRecord();a.actionId=id;a.idempotencyKey=key;a.capabilityId=cap;a.params=new LinkedHashMap<>(p);a.environmentId=env;
        a.deadline=deadline;a.createdAt=Ids.now();a.expectedRevisions=revs==null?Map.of():new LinkedHashMap<>(revs);a.runId=runId;a.goalVersion=goalVersion;
        a.status="QUEUED";actionsById.put(id,a);actionsByKey.put(key,a);
        var validation=registry.validate(cap,p);
        String invalid=precondition(a);
        if(!validation.ok() || invalid!=null) return finish(a,"NOT_APPLIED",invalid!=null?invalid:validation.code());
        if(consume(FaultType.REJECT,cap)) return finish(a,"NOT_APPLIED","DEVICE_REJECTED");
        if(consume(FaultType.ACK_NOT_APPLIED,cap)) return finish(a,"NOT_APPLIED","ACK_NOT_APPLIED");
        if(consume(FaultType.DELAY_APPLY,cap)) {a.applyAfterMs=System.currentTimeMillis()+100;a.message="ACCEPTED";commit();return a;}
        if(consume(FaultType.TOOL_TIMEOUT,cap)){a.message="TIMEOUT";commit();throw new SimulatorException("RESPONSE_LOST","设备响应超时",id);}
        apply(a);
        if(consume(FaultType.APPLIED_RESPONSE_LOST,cap)) throw new SimulatorException("RESPONSE_LOST","响应丢失，执行终局需查询",id);
        return a;
    }
    private String precondition(ActionRecord a){
        if(!environmentId.equals(a.environmentId)) return "ENVIRONMENT_MISMATCH";
        if(a.deadline!=null && Instant.now().isAfter(a.deadline)) return "DEADLINE_EXCEEDED";
        for(String d:registry.get(a.capabilityId).map(CapabilityDefinition::getDomains).orElse(Set.of()))
            if(a.expectedRevisions.containsKey(d)&&!Objects.equals(a.expectedRevisions.get(d),revisions.get(d))) return "REVISION_CONFLICT";
        return null;
    }
    private void apply(ActionRecord a){
        String invalid=precondition(a);if(invalid!=null){finish(a,"NOT_APPLIED",invalid);return;}
        String cap=registry.canonical(a.capabilityId);
        String navFail=navigationPrecheck(cap,a.params);
        if(navFail!=null){finish(a,"NOT_APPLIED",navFail);return;}
        var updates=new LinkedHashMap<>(CapabilityEffects.expected(cap,a.params));
        if("media.play".equals(cap)) updates.put("media_track","公开占位曲目 · 无音频");
        applyNavigationEffects(cap,a.params,updates);
        applyLifeEffects(cap,a.params,updates);
        if(updates.isEmpty() && !cap.startsWith("navigation.query_") && !cap.startsWith("life.")) {
            // keep expected empty only for unknown
        }
        change(updates,"AGENT_ACTION",a);a.revision=revision;finish(a,"APPLIED","OK");
    }

    /** Known POIs for honest search; unknown destination → SEARCH_NO_CANDIDATE (no fake success). */
    private static final Set<String> KNOWN_POIS = Set.of(
            "东方明珠","虹桥机场","浦东机场","固安","星巴克","加油站","迪士尼",
            "上海游泳馆","浦东美术馆","鼋头渚","灵山大佛","三凤桥","无锡国际会议中心",
            "虹桥幸福里","陆家嘴办公楼");

    private String navigationPrecheck(String cap, Map<String,Object> p){
        return switch(cap){
            case "navigation.start","navigation.set_route" -> {
                String dest=String.valueOf(p.get("destination")).trim();
                yield poiResolvable(dest)?null:"SEARCH_NO_CANDIDATE";
            }
            case "navigation.navigate_home" -> state.get("navigation_home")==null?"NEED_SET_HOME":null;
            case "navigation.navigate_company" -> state.get("navigation_company")==null?"NEED_SET_COMPANY":null;
            case "navigation.pause","navigation.resume" -> Boolean.TRUE.equals(state.get("navigation_active"))?null:"NOT_NAVIGATING";
            case "navigation.add_waypoint" -> {
                if(!Boolean.TRUE.equals(state.get("navigation_active")) || state.get("navigation_destination")==null)
                    yield "NO_ACTIVE_DESTINATION";
                String name=String.valueOf(p.get("name")).trim();
                yield poiResolvable(name)?null:"SEARCH_NO_CANDIDATE";
            }
            case "navigation.remove_waypoint" -> {
                if(!Boolean.TRUE.equals(state.get("navigation_active"))) yield "NOT_NAVIGATING";
                Object wp=state.get("navigation_waypoints");
                boolean has=wp instanceof List<?> list && list.contains(p.get("name"));
                yield has?null:"WAYPOINT_NOT_FOUND";
            }
            default -> null;
        };
    }

    private boolean poiResolvable(String name){
        if(name==null || name.isBlank()) return false;
        if(KNOWN_POIS.contains(name)) return true;
        // allow favorite aliases and common category words already in KNOWN_POIS
        Object home=state.get("navigation_home");
        Object company=state.get("navigation_company");
        return name.equals(home) || name.equals(company) || name.equals("家") || name.equals("公司");
    }

    @SuppressWarnings("unchecked")
    private void applyNavigationEffects(String cap, Map<String,Object> p, Map<String,Object> updates){
        switch(cap){
            case "navigation.start","navigation.set_route" -> {
                updates.put("navigation_active",true);
                updates.put("navigation_destination",p.get("destination"));
                updates.put("navigation_paused",false);
                updates.put("navigation_waypoints",new ArrayList<String>());
                updates.put("route_points",List.of(List.of(-2,0),List.of(-1,1),List.of(1,1),List.of(2,2)));
                updates.put("navigation_eta_minutes",etaMinutes(0));
                clearNavQuery(updates);
                closeLifeSession(updates); // 明确开航打断外卖会话
            }
            case "navigation.stop","navigation.exit","navigation.nav_exit" -> {
                updates.put("navigation_active",false);
                updates.put("navigation_destination",null);
                updates.put("navigation_paused",false);
                updates.put("navigation_waypoints",new ArrayList<String>());
                updates.put("route_points",List.of());
                updates.put("navigation_eta_minutes",null);
                clearNavQuery(updates);
            }
            case "navigation.pause" -> updates.put("navigation_paused",true);
            case "navigation.resume" -> updates.put("navigation_paused",false);
            case "navigation.add_waypoint" -> {
                List<String> next=new ArrayList<>(waypointList());
                String name=String.valueOf(p.get("name"));
                if(!next.contains(name)) next.add(name);
                updates.put("navigation_waypoints",next);
                updates.put("navigation_eta_minutes",etaMinutes(next.size()));
                // 途经不丢终点：destination 保持不变
                updates.put("navigation_destination",state.get("navigation_destination"));
                updates.put("navigation_active",true);
            }
            case "navigation.remove_waypoint" -> {
                List<String> next=new ArrayList<>(waypointList());
                next.remove(String.valueOf(p.get("name")));
                updates.put("navigation_waypoints",next);
                updates.put("navigation_eta_minutes",etaMinutes(next.size()));
                updates.put("navigation_destination",state.get("navigation_destination"));
                updates.put("navigation_active",true);
            }
            case "navigation.navigate_home" -> {
                Object home=state.get("navigation_home");
                updates.put("navigation_active",true);
                updates.put("navigation_destination",home);
                updates.put("navigation_paused",false);
                updates.put("navigation_waypoints",new ArrayList<String>());
                updates.put("route_points",List.of(List.of(-2,0),List.of(0,1),List.of(2,2)));
                updates.put("navigation_eta_minutes",etaMinutes(0));
                clearNavQuery(updates);
                closeLifeSession(updates);
            }
            case "navigation.navigate_company" -> {
                Object company=state.get("navigation_company");
                updates.put("navigation_active",true);
                updates.put("navigation_destination",company);
                updates.put("navigation_paused",false);
                updates.put("navigation_waypoints",new ArrayList<String>());
                updates.put("route_points",List.of(List.of(-1,0),List.of(1,1),List.of(2,0)));
                updates.put("navigation_eta_minutes",etaMinutes(0));
                clearNavQuery(updates);
                closeLifeSession(updates);
            }
            case "navigation.query_eta" -> {
                boolean active=Boolean.TRUE.equals(state.get("navigation_active"));
                updates.put("last_nav_query_type","eta");
                updates.put("last_nav_query_result", active
                        ? "预计剩余 "+state.getOrDefault("navigation_eta_minutes",15)+" 分钟到达 "+state.get("navigation_destination")
                        : "当前未在导航中，无法提供 ETA");
            }
            case "navigation.query_status" -> {
                boolean active=Boolean.TRUE.equals(state.get("navigation_active"));
                updates.put("last_nav_query_type","status");
                updates.put("last_nav_query_result", active
                        ? "导航中，目的地 "+state.get("navigation_destination")
                          +(Boolean.TRUE.equals(state.get("navigation_paused"))?"（已暂停）":"")
                          +"，偏好 "+state.get("navigation_preference")
                        : "当前未在导航");
            }
            case "navigation.query_waypoints" -> {
                updates.put("last_nav_query_type","waypoints");
                List<String> wps=waypointList();
                updates.put("last_nav_query_result", wps.isEmpty() ? "当前无途经点" : "途经点："+String.join("、", wps));
            }
            default -> {}
        }
    }

    private void applyLifeEffects(String cap, Map<String,Object> p, Map<String,Object> updates){
        switch(cap){
            case "life.search_shops" -> {
                updates.put("life_session_active",true);
                updates.put("life_phase","shop_list");
                updates.put("life_last_keyword",p.get("keyword"));
            }
            case "life.enter_shop" -> {
                updates.put("life_session_active",true);
                updates.put("life_phase","in_shop");
                updates.put("life_last_shop",p.get("shop_name"));
            }
            case "life.add_to_cart" -> {
                updates.put("life_session_active",true);
                updates.put("life_phase","in_shop");
                updates.put("life_last_item",p.get("item"));
            }
            case "life.go_to_checkout" -> {
                updates.put("life_session_active",true);
                updates.put("life_phase","checkout");
            }
            case "life.close" -> {
                updates.put("life_session_active",false);
                updates.put("life_phase","idle");
                updates.put("life_last_keyword",null);
                updates.put("life_last_shop",null);
                updates.put("life_last_item",null);
            }
            default -> {}
        }
    }

    private void clearNavQuery(Map<String,Object> updates){
        updates.put("last_nav_query_type",null);
        updates.put("last_nav_query_result",null);
    }

    /** 导航开航抢域：关闭生活服务会话，不宣称完成点单。 */
    private void closeLifeSession(Map<String,Object> updates){
        updates.put("life_session_active",false);
        updates.put("life_phase","idle");
        updates.put("life_last_keyword",null);
        updates.put("life_last_shop",null);
        updates.put("life_last_item",null);
    }

    @SuppressWarnings("unchecked")
    private List<String> waypointList(){
        Object wp=state.get("navigation_waypoints");
        if(wp instanceof List<?> list){
            List<String> out=new ArrayList<>();
            for(Object o:list) out.add(String.valueOf(o));
            return out;
        }
        return new ArrayList<>();
    }

    private int etaMinutes(int waypointCount){
        return 12 + waypointCount * 8;
    }
    public synchronized ActionRecord queryAction(String id){return actionsById.get(id);}
    /** Environment clock advances queued commands and prompt events, never the Harness verifier. */
    public synchronized void tick(){
        boolean changed=false;
        for(var a:new ArrayList<>(actionsById.values())) if("QUEUED".equals(a.status)&&a.applyAfterMs>0&&System.currentTimeMillis()>=a.applyAfterMs){apply(a);changed=true;}
        Object prev=state.get("last_prompt_at");
        if(Boolean.TRUE.equals(state.get("navigation_active")) && (prev==null || Instant.parse(prev.toString()).isBefore(Instant.now().minusMillis(500)))){emitPromptEvent();changed=true;}
        if(changed) commit();
    }
    public synchronized void emitPromptEvent(){
        boolean played=Boolean.TRUE.equals(state.get("navigation_active"))&&Boolean.TRUE.equals(state.get("prompt_enabled"))&&!Boolean.TRUE.equals(state.get("navigation_muted"))&&((Number)state.get("navigation_volume")).intValue()>0&&Boolean.TRUE.equals(state.get("route_available"))&&Boolean.TRUE.equals(state.get("focus_available"));
        change(Ids.dict("last_prompt_event_id",Ids.newId("prompt"),"last_prompt_at",Ids.now().toString(),"last_prompt_result",played?"PLAYED":"BLOCKED","last_prompt_navigation_revision",revisions.get("NAVIGATION")),"EXTERNAL",null);commit();
    }
    public synchronized void applyInitialState(Map<String,Object> fields){if(fields!=null)fields.forEach(this::externalChange);}
    public synchronized void externalChange(String field,Object value){
        if(!state.containsKey(field)) throw new SimulatorException("UNSUPPORTED_FIELD","不支持字段 "+field);
        Object old=state.get(field);
        if(old instanceof Boolean && !(value instanceof Boolean)) throw new IllegalArgumentException("boolean required");
        if(old instanceof Number && !(value instanceof Number)) throw new IllegalArgumentException("number required");
        if(value instanceof Number n){
            int min=0,max=10;
            if(field.startsWith("window_")) max=100;
            if(field.equals("temperature_setpoint")){min=16;max=30;}
            if(field.equals("cabin_temperature")){min=-30;max=70;}
            if(field.equals("fan_level")) max=3;
            if(field.equals("navigation_eta_minutes")){min=0;max=600;}
            if(!field.startsWith("last_")&&(n.doubleValue()!=n.intValue()||n.intValue()<min||n.intValue()>max))
                throw new IllegalArgumentException("field out of range");
        }
        Map<String,Object> updates=Ids.dict(field,value);
        if("window_open".equals(field)) CapabilityRegistry.WINDOWS.forEach(w->updates.put("window_"+w,Boolean.TRUE.equals(value)?100:0));
        change(updates,"EXTERNAL",null);commit();
    }
    private void change(Map<String,Object> updates,String source,ActionRecord a){
        revision++;var touched=new HashSet<String>();
        for(var e:updates.entrySet()){
            state.put(e.getKey(),e.getValue());touched.add(domain(e.getKey()));
            origins.put(e.getKey(),Ids.dict("run_id",a==null?null:a.runId,"action_id",a==null?null:a.actionId,"goal_version",a==null?null:a.goalVersion,"environment_id",environmentId,"revision",revision,"origin",source,"observed_at",Ids.now().toString()));
        }
        state.put("window_open",CapabilityRegistry.WINDOWS.stream().anyMatch(w -> ((Number)state.get("window_"+w)).intValue()>0));
        touched.forEach(d->revisions.merge(d,1L,Long::sum));
    }
    private String domain(String field){
        if(field.startsWith("media_")) return "MEDIA";
        if(field.startsWith("life_")) return "LIFE";
        if(field.startsWith("last_")||field.equals("route_available")||field.equals("focus_available")) return "AUDIO";
        if(field.startsWith("navigation_")||field.equals("prompt_enabled")||field.equals("route_points")
                ||field.equals("last_nav_query_type")||field.equals("last_nav_query_result")) return "NAVIGATION";
        return "CABIN";
    }
    private ActionRecord finish(ActionRecord a,String status,String msg){a.status=status;a.message=msg;a.finishedAt=Ids.now();commit();return a;}
    private void commit(){
        persistence.accept(exportState());
        Map<String,Object> v=view();
        for(Consumer<Map<String,Object>> listener:changeListeners) listener.accept(v);
    }
    public synchronized Map<String,Object> exportState(){return Ids.dict("environment_id",environmentId,"revision",revision,"state",new LinkedHashMap<>(state),"revisions",new LinkedHashMap<>(revisions),"origins",new LinkedHashMap<>(origins),"actions",new ArrayList<>(actionsById.values()));}
    @SuppressWarnings("unchecked")
    public synchronized void restore(Map<String,Object> saved,com.fasterxml.jackson.databind.ObjectMapper mapper){
        environmentId=(String)saved.get("environment_id");revision=((Number)saved.get("revision")).longValue();
        state.clear();state.putAll((Map<String,Object>)saved.get("state"));revisions.clear();((Map<String,Number>)saved.get("revisions")).forEach((k,v)->revisions.put(k,v.longValue()));
        origins.clear();origins.putAll((Map<String,Map<String,Object>>)saved.get("origins"));actionsById.clear();actionsByKey.clear();
        for(Object raw:(List<?>)saved.get("actions")){var a=mapper.convertValue(raw,ActionRecord.class);actionsById.put(a.actionId,a);actionsByKey.put(a.idempotencyKey,a);}
    }
    public synchronized void terminateQueuedActions(){for(var a:actionsById.values())if("QUEUED".equals(a.status))finish(a,"NOT_APPLIED","INTERRUPTED_QUEUED");}
    public synchronized Map<String,Object> view(){
        var s=snapshot();var windows=new LinkedHashMap<String,Object>();CapabilityRegistry.WINDOWS.forEach(w->windows.put(w,state.get("window_"+w)));
        return Ids.dict("device_id",getDeviceId(),"environment_id",environmentId,"revision",revision,"observed_at",s.getObservedAt(),"domain_revisions",s.getDomainRevisions(),"origins",s.getOrigins(),"state",s.getState(),"simulation",true,
          "climate",Ids.dict("power",state.get("climate_power"),"setpoint",state.get("temperature_setpoint"),"cabin_temperature",state.get("cabin_temperature"),"fan_level",state.get("fan_level")),"windows",windows,
          "media",Ids.dict("playing",state.get("media_playing"),"track",state.get("media_track"),"artist",state.get("media_artist"),"volume",state.get("media_volume")),
          "navigation",Ids.dict(
                  "active",state.get("navigation_active"),
                  "destination",state.get("navigation_destination"),
                  "paused",state.get("navigation_paused"),
                  "waypoints",state.get("navigation_waypoints"),
                  "preference",state.get("navigation_preference"),
                  "eta_minutes",state.get("navigation_eta_minutes"),
                  "home",state.get("navigation_home"),
                  "company",state.get("navigation_company"),
                  "prompt_enabled",state.get("prompt_enabled"),
                  "volume",state.get("navigation_volume"),
                  "route_points",state.get("route_points"),
                  "last_query",state.get("last_nav_query_result")),
          "life",Ids.dict(
                  "session_active",state.get("life_session_active"),
                  "phase",state.get("life_phase"),
                  "last_keyword",state.get("life_last_keyword"),
                  "last_shop",state.get("life_last_shop"),
                  "last_item",state.get("life_last_item")));
    }
}
