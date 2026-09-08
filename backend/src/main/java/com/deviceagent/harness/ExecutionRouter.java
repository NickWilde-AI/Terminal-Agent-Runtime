package com.deviceagent.harness;
import com.deviceagent.domain.RouteType;
import com.deviceagent.model.CompiledTaskCandidate;
/** Routing sees validated structured intent only. */
public class ExecutionRouter {
    public RouteType route(CompiledTaskCandidate c){
        if(c.rejectReason!=null&&!c.rejectReason.isBlank())return RouteType.REJECT;
        if(c.clarifyQuestion!=null&&!c.clarifyQuestion.isBlank())return RouteType.CLARIFY;
        return c.goals.size()==1&&c.constraints.isEmpty()&&!"AGENT".equals(c.routeHint)?RouteType.FAST:RouteType.AGENT;
    }
}
