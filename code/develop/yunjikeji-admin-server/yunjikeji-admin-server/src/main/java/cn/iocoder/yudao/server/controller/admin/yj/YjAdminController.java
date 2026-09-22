package cn.iocoder.yudao.server.controller.admin.yj;

import cn.iocoder.yudao.framework.common.pojo.CommonResult;
import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.server.service.yj.YjAdminService;
import cn.iocoder.yudao.server.service.yj.YjAdminTableRegistry.TableMeta;
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.*;

import javax.annotation.Resource;
import java.util.Collection;
import java.util.Map;

import static cn.iocoder.yudao.framework.common.pojo.CommonResult.success;

@Tag(name = "管理后台 - 云技业务管理")
@RestController
@RequestMapping("/yj")
@Validated
public class YjAdminController {

    @Resource
    private YjAdminService yjAdminService;

    @GetMapping("/resources")
    @Operation(summary = "获得云技后台资源清单")
    public CommonResult<Collection<TableMeta>> getResources() {
        return success(yjAdminService.listResources());
    }

    @GetMapping("/{resource}/page")
    @Operation(summary = "获得云技业务资源分页")
    public CommonResult<PageResult<Map<String, Object>>> getPage(@PathVariable("resource") String resource,
                                                                 @RequestParam Map<String, String> params) {
        return success(yjAdminService.getPage(resource, params));
    }

    @GetMapping("/{resource}/get")
    @Operation(summary = "获得云技业务资源详情")
    public CommonResult<Map<String, Object>> get(@PathVariable("resource") String resource,
                                                 @RequestParam("id") Long id) {
        return success(yjAdminService.get(resource, id));
    }

    @PostMapping("/agent/sync-qwenpaw")
    @Operation(summary = "同步 QwenPaw 智能体")
    public CommonResult<Map<String, Object>> syncQwenPawAgents() {
        return success(yjAdminService.syncQwenPawAgents());
    }

    @PostMapping("/agent/call-qwenpaw")
    @Operation(summary = "调用 QwenPaw 智能体")
    public CommonResult<Map<String, Object>> callQwenPawAgent(@RequestBody Map<String, Object> body) {
        return success(yjAdminService.callQwenPawAgent(body));
    }

    @PostMapping("/{resource}/create")
    @Operation(summary = "创建云技业务资源")
    public CommonResult<Long> create(@PathVariable("resource") String resource,
                                     @RequestBody Map<String, Object> body) {
        return success(yjAdminService.create(resource, body));
    }

    @PutMapping("/{resource}/update")
    @Operation(summary = "更新云技业务资源")
    public CommonResult<Boolean> update(@PathVariable("resource") String resource,
                                        @RequestBody Map<String, Object> body) {
        yjAdminService.update(resource, body);
        return success(true);
    }

    @DeleteMapping("/{resource}/delete")
    @Operation(summary = "删除云技业务资源")
    public CommonResult<Boolean> delete(@PathVariable("resource") String resource,
                                        @RequestParam("id") Long id) {
        yjAdminService.delete(resource, id);
        return success(true);
    }
}
