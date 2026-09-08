package com.deviceagent.harness;
import com.deviceagent.domain.*;
import com.deviceagent.model.CompiledTaskCandidate;
import com.deviceagent.capability.*;
import org.springframework.stereotype.Component;
import java.util.*;

/** Only the product contract creates required predicates; model criteria cannot weaken them. */
@Component
public class TaskBinder {
    private final CapabilityRegistry registry=new CapabilityRegistry();
    public DeviceTask bind(String runId,String text,String defaults,CompiledTaskCandidate candidate){
        var t=new DeviceTask();t.setRunId(runId);t.setRawText(text);t.setDefaultsRuleId(defaults);
        t.setGoals(new ArrayList<>(candidate.goals));t.setConstraints(new ArrayList<>(candidate.constraints));
        for(var g:t.getGoals()) {
            Map<String,Object> action=actionFor(g);
            if(action==null){
                // Observation-only goals (no write) — skip product predicates
                if("nav_diagnostic".equals(g.get("type"))||"media_keep_muted".equals(g.get("type"))) continue;
                throw new IllegalArgumentException("未注册目标类型: "+g.get("type"));
            }
            String cap=(String)action.get("capability_id");Map<String,Object> p=params(action);
            var v=registry.validate(cap,p);if(!v.ok())throw new IllegalArgumentException(v.message());
            for(var e:CapabilityEffects.expected(cap,p).entrySet()) add(t,"field_eq",Ids.dict("field",e.getKey(),"value",e.getValue()),String.valueOf(g.getOrDefault("source","user")));
        }
        for(var c:t.getConstraints()) if("keep_navigation_prompt".equals(c.get("type"))) add(t,"nav_prompt_retained",Ids.dict("min_volume",c.getOrDefault("min_volume",1)),"user");
        // Audio diagnostic has a fixed product predicate, never a model-defined expression.
        if(candidate.criteria.stream().anyMatch(c -> "nav_prompt_event_played".equals(c.get("template_id")))) add(t,"nav_prompt_event_played",Map.of(),"diagnostic contract");
        if(t.getCriteria().isEmpty()) throw new IllegalArgumentException("没有可验收目标，需澄清");
        t.getBindingContext().put("summary",candidate.summary);return t;
    }
    private void add(DeviceTask t,String template,Map<String,Object> p,String source){var c=new Criterion();c.setCriterionId("c"+(t.getCriteria().size()+1));c.setTemplateId(template);c.setParams(p);c.setRequired(true);c.setSourceRef(source);c.setBoundAt(Ids.now());c.setBoundGoalVersion(t.getGoalVersion());t.getCriteria().add(c);}
    @SuppressWarnings("unchecked") public static Map<String,Object> params(Map<String,Object> action){return action.get("params") instanceof Map<?,?> p ? new LinkedHashMap<>((Map<String,Object>)p):Map.of();}
    public static Map<String,Object> actionFor(Map<String,Object> g){
        if(g.containsKey("capability_id")) return Ids.dict("capability_id",g.get("capability_id"),"params",g.getOrDefault("params",Map.of()));
        String type=String.valueOf(g.get("type"));
        return switch(type){
            case "climate_power" -> Ids.dict("capability_id","climate.set_power","params",Ids.dict("value",g.get("value")));
            case "cabin_temperature" -> Ids.dict("capability_id","climate.set_temperature","params",Ids.dict("value",g.get("value")));
            case "cabin_fan" -> Ids.dict("capability_id","climate.set_fan","params",Ids.dict("value",g.get("value")));
            case "window_position" -> Ids.dict("capability_id","window.set_position","params",Ids.dict("window",g.getOrDefault("window","all"),"position",g.get("position")));
            case "media_play" -> Ids.dict("capability_id","media.play","params",Ids.dict("artist",g.get("artist")));
            case "media_pause" -> Ids.dict("capability_id","media.pause","params",Map.of());
            case "media_volume" -> Ids.dict("capability_id","media.set_volume","params",Ids.dict("value",g.get("value")));
            case "nav_start" -> Ids.dict("capability_id","navigation.start","params",Ids.dict("destination",g.get("destination")));
            case "nav_stop" -> Ids.dict("capability_id","navigation.stop","params",Map.of());
            case "nav_prompt_enabled" -> Ids.dict("capability_id","navigation.set_prompt_enabled","params",Ids.dict("value",g.get("value")));
            case "nav_volume" -> Ids.dict("capability_id","navigation.set_volume","params",Ids.dict("value",g.get("value")));
            case "nav_muted" -> Ids.dict("capability_id","navigation.set_muted","params",Ids.dict("value",g.get("value")));
            default -> null;
        };
    }
}
