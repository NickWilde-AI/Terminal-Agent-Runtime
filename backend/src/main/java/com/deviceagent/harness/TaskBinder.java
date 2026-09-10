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
            String cap=registry.canonical((String)action.get("capability_id"));Map<String,Object> p=params(action);
            var v=registry.validate(cap,p);if(!v.ok())throw new IllegalArgumentException(v.message());
            var expected=CapabilityEffects.expected(cap,p);
            if(expected.isEmpty()){
                String src=String.valueOf(g.getOrDefault("source","user"));
                switch(cap){
                    case "navigation.add_waypoint" -> add(t,"nav_waypoint_contains",Ids.dict("name",p.get("name")),src);
                    case "navigation.remove_waypoint" -> add(t,"nav_waypoint_absent",Ids.dict("name",p.get("name")),src);
                    case "navigation.query_eta" -> add(t,"nav_query_type",Ids.dict("type","eta"),src);
                    case "navigation.query_status" -> add(t,"nav_query_type",Ids.dict("type","status"),src);
                    case "navigation.query_waypoints" -> add(t,"nav_query_type",Ids.dict("type","waypoints"),src);
                    default -> throw new IllegalArgumentException("无法为能力生成验收条件: "+cap);
                }
            } else {
                for(var e:expected.entrySet()) add(t,"field_eq",Ids.dict("field",e.getKey(),"value",e.getValue()),String.valueOf(g.getOrDefault("source","user")));
            }
            // 途经不丢终点：追加途经时额外验收终点仍在
            if("navigation.add_waypoint".equals(cap) && g.get("retain_destination")!=null){
                add(t,"field_eq",Ids.dict("field","navigation_destination","value",g.get("retain_destination")),"user");
            }
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
            case "nav_pause" -> Ids.dict("capability_id","navigation.pause","params",Map.of());
            case "nav_resume" -> Ids.dict("capability_id","navigation.resume","params",Map.of());
            case "nav_add_waypoint" -> Ids.dict("capability_id","navigation.add_waypoint","params",Ids.dict("name",g.get("name")));
            case "nav_remove_waypoint" -> Ids.dict("capability_id","navigation.remove_waypoint","params",Ids.dict("name",g.get("name")));
            case "nav_preference" -> Ids.dict("capability_id","navigation.set_preference","params",Ids.dict("value",g.get("value")));
            case "nav_home" -> Ids.dict("capability_id","navigation.navigate_home","params",Map.of());
            case "nav_company" -> Ids.dict("capability_id","navigation.navigate_company","params",Map.of());
            case "nav_set_home" -> Ids.dict("capability_id","navigation.set_home","params",Ids.dict("place",g.get("place")));
            case "nav_set_company" -> Ids.dict("capability_id","navigation.set_company","params",Ids.dict("place",g.get("place")));
            case "nav_query_eta" -> Ids.dict("capability_id","navigation.query_eta","params",Map.of());
            case "nav_query_status" -> Ids.dict("capability_id","navigation.query_status","params",Map.of());
            case "nav_query_waypoints" -> Ids.dict("capability_id","navigation.query_waypoints","params",Map.of());
            case "nav_prompt_enabled" -> Ids.dict("capability_id","navigation.set_prompt_enabled","params",Ids.dict("value",g.get("value")));
            case "nav_volume" -> Ids.dict("capability_id","navigation.set_volume","params",Ids.dict("value",g.get("value")));
            case "nav_muted" -> Ids.dict("capability_id","navigation.set_muted","params",Ids.dict("value",g.get("value")));
            case "life_search_shops" -> Ids.dict("capability_id","life.search_shops","params",Ids.dict("keyword",g.get("keyword")));
            case "life_enter_shop" -> Ids.dict("capability_id","life.enter_shop","params",Ids.dict("shop_name",g.get("shop_name")));
            case "life_add_to_cart" -> Ids.dict("capability_id","life.add_to_cart","params",Ids.dict("item",g.get("item")));
            case "life_go_to_checkout" -> Ids.dict("capability_id","life.go_to_checkout","params",Map.of());
            case "life_close" -> Ids.dict("capability_id","life.close","params",Map.of());
            default -> null;
        };
    }
}
