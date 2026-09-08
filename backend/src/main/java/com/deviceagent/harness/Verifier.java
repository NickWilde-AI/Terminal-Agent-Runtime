package com.deviceagent.harness;
import com.deviceagent.capability.CapabilityEffects;
import com.deviceagent.device.DevicePort;
import com.deviceagent.domain.*;
import org.springframework.stereotype.Component;
import java.time.Instant;
import java.util.*;
@Component
public class Verifier {
    private final DevicePort device;
    public Verifier(DevicePort device){this.device=device;}
    public Result verifyTask(RunRecord run){
        StateSnapshot s;
        try{run.getBudget().countTool();s=device.readState(null);}catch(Exception e){return new Result(GoalOutcome.UNKNOWN,"验证不可用，不能确认目标已满足",List.of(Ids.dict("status","UNKNOWN","detail","读取不可用")),device.snapshot());}
        var details=new ArrayList<Map<String,Object>>();
        boolean fresh=s.getObservedAt()!=null&&s.getObservedAt().isAfter(Instant.now().minusSeconds(2))&&Objects.equals(s.getEnvironmentId(),run.getEnvironmentId());
        for(var c:run.getTask().getCriteria()){
            String status=!fresh?"UNKNOWN":check(c,s)?"SATISFIED":"NOT_SATISFIED";
            details.add(Ids.dict("criterion_id",c.getCriterionId(),"template_id",c.getTemplateId(),"params",c.getParams(),"status",status));
        }
        boolean unresolved=run.isUnresolvedUnknown()||run.getActions().stream().anyMatch(a->a.getExecutionStatus()==ExecutionStatus.UNKNOWN);
        var outcome=unresolved||!fresh?GoalOutcome.UNKNOWN:!details.isEmpty()&&details.stream().allMatch(d->"SATISFIED".equals(d.get("status")))?GoalOutcome.SATISFIED:GoalOutcome.UNSATISFIED;
        String summary=outcome==GoalOutcome.UNKNOWN?"结果未知，保留已知动作事实，停止新写":outcome==GoalOutcome.UNSATISFIED?"仍有目标未满足，请查看逐项证据":summary(run,s);
        return new Result(outcome,summary,details,s);
    }
    public static boolean check(Criterion c,StateSnapshot s){
        var m=s.getState();var p=c.getParams();
        return switch(c.getTemplateId()){
            case "field_eq" -> CapabilityEffects.eq(m.get(String.valueOf(p.get("field"))),p.get("value"));
            case "cabin_temperature_eq" -> CapabilityEffects.eq(m.get("temperature_setpoint"),p.get("value"));
            case "cabin_fan_eq" -> CapabilityEffects.eq(m.get("fan_level"),p.get("value"));
            case "media_volume_eq" -> CapabilityEffects.eq(m.get("media_volume"),p.get("value"));
            case "nav_prompt_retained" -> Boolean.TRUE.equals(m.get("navigation_active"))&&Boolean.TRUE.equals(m.get("prompt_enabled"))&&!Boolean.TRUE.equals(m.get("navigation_muted"))&&Boolean.TRUE.equals(m.get("route_available"))&&Boolean.TRUE.equals(m.get("focus_available"))&&((Number)m.get("navigation_volume")).intValue()>=((Number)p.getOrDefault("min_volume",1)).intValue();
            case "nav_prompt_event_played" -> "PLAYED".equals(m.get("last_prompt_result"))&&m.get("last_prompt_at")!=null&&c.getBoundAt()!=null&&Instant.parse(m.get("last_prompt_at").toString()).isAfter(c.getBoundAt())&&CapabilityEffects.eq(m.get("last_prompt_navigation_revision"),s.getDomainRevisions().get("NAVIGATION"));
            default -> false;
        };
    }
    private String summary(RunRecord r,StateSnapshot s){
        var st=s.getState();
        long verified=r.getActions().stream().filter(a->a.getExecutionStatus()==ExecutionStatus.APPLIED&&a.getAttribution()==Attribution.THIS_ACTION&&a.getVerificationStatus()==VerificationStatus.SATISFIED).count();
        StringBuilder sb=new StringBuilder();
        if(verified>0) sb.append("当前目标已满足；").append(verified).append(" 项动作有应用与回读证据。");
        else sb.append("当前设定已是目标值，无需重复写入。");
        sb.append(" 空调电源 ").append(Boolean.TRUE.equals(st.get("climate_power"))?"开":"关");
        sb.append("，设定 ").append(st.get("temperature_setpoint")).append("℃");
        sb.append("，舱温 ").append(st.get("cabin_temperature")).append("℃（设定温度≠当前舱温）");
        sb.append("。车窗 左前/右前/左后/右后 ")
                .append(st.get("window_front_left")).append("/")
                .append(st.get("window_front_right")).append("/")
                .append(st.get("window_rear_left")).append("/")
                .append(st.get("window_rear_right"));
        if(Boolean.TRUE.equals(st.get("media_playing"))) {
            sb.append("。媒体播放中（占位曲目，无真实音频）");
        } else {
            sb.append("。媒体未播放");
        }
        if(Boolean.TRUE.equals(st.get("navigation_active"))) {
            sb.append("。导航进行中 → ").append(st.getOrDefault("navigation_destination","—"));
            sb.append("（播报开关开启≠用户已听到声音）");
        }
        sb.append("。以上为本地模拟器状态，不代表真实设备。");
        return sb.toString();
    }
    public record Result(GoalOutcome outcome,String summary,List<Map<String,Object>> details,StateSnapshot snapshot){}
}
