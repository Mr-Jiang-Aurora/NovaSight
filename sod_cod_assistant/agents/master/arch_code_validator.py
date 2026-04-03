"""
架构图与代码双向验证器
对比 Agent4 的架构图识别结果和 Agent3 的代码分析结果，
输出详细的对应关系验证报告。
"""

import re
import logging

logger = logging.getLogger(__name__)


class ArchCodeValidator:
    """架构图与代码双向验证器"""

    def validate(self, arch_hint, code_analysis):
        """
        主入口：执行双向验证。

        Args:
            arch_hint:     Agent4 的架构图解析结果（ArchHint）
            code_analysis: Agent3 的代码分析结果（UserCodeAnalysis）

        Returns:
            ArchCodeValidationReport 详细验证报告
        """
        from shared.models import ArchCodeValidationReport

        report = ArchCodeValidationReport()

        # Step 1：从架构图提取所有声称的模块
        arch_modules = self._extract_arch_modules(arch_hint)
        logger.info(f"[Validator] 架构图声称模块：{list(arch_modules.keys())}")

        # Step 2：从代码分析提取所有实现的模块
        code_modules = self._extract_code_modules(code_analysis)
        logger.info(f"[Validator] 代码实现模块：{list(code_modules.keys())}")

        # Step 3：双向匹配
        for arch_name, arch_desc in arch_modules.items():
            match_result = self._match_arch_to_code(arch_name, arch_desc, code_modules)
            report.arch_to_code_matches.append(match_result)

        # Step 4：找出代码中有但图里没画的模块（个性化 note）
        for code_name, code_info in code_modules.items():
            if not self._is_mentioned_in_arch(code_name, arch_hint):
                cn_lower = code_name.lower()
                if any(kw in cn_lower for kw in ["residual", "skip", "shortcut"]):
                    note = "残差/跳跃连接模块，通常不在架构概览图中单独标注，属于实现层面细节"
                elif any(kw in cn_lower for kw in ["norm", "bn", "ln", "layernorm", "batchnorm"]):
                    note = "归一化层，架构图通常省略，属于子模块实现细节"
                elif any(kw in cn_lower for kw in ["loss", "criterion"]):
                    note = "损失函数模块，训练时使用，推理架构图中通常不画"
                elif any(kw in cn_lower for kw in ["data", "loader", "dataset"]):
                    note = "数据加载模块，与推理架构无关，架构图不包含"
                elif any(kw in cn_lower for kw in ["embed", "pos", "patch"]):
                    note = "位置编码/Patch嵌入模块，Transformer子组件，架构图一般合并在编码器框内"
                elif any(kw in cn_lower for kw in ["head", "classifier", "linear"]):
                    note = "输出头/分类层，架构图通常简化为最终输出箭头，未单独画出"
                else:
                    note = "代码中存在但架构图未画出；可能是辅助模块、调试组件或后期新增功能"
                report.code_only_modules.append({
                    "name":     code_name,
                    "location": code_info.get("location", ""),
                    "type":     code_info.get("type", "module"),
                    "note":     note,
                })

        # Step 5：统计和评分
        verified  = sum(1 for m in report.arch_to_code_matches if m.status == "verified")
        missing   = sum(1 for m in report.arch_to_code_matches if m.status == "missing")
        partial   = sum(1 for m in report.arch_to_code_matches if m.status == "partial")
        total_arch = len(report.arch_to_code_matches)

        report.total_arch_modules = total_arch
        report.verified_count     = verified
        report.missing_count      = missing
        report.partial_count      = partial
        report.code_only_count    = len(report.code_only_modules)
        report.consistency_score  = round(
            (verified + 0.5 * partial) / max(total_arch, 1) * 100, 1
        )

        # Step 6：生成结论
        report.conclusion = self._generate_conclusion(report)
        logger.info(
            f"[Validator] 验证完成：一致性={report.consistency_score}%，"
            f"已验证={verified}/{total_arch}"
        )

        return report

    def _extract_arch_modules(self, hint) -> dict:
        """从 ArchHint 提取所有声称的模块名（修复括号截断问题）"""
        modules: dict = {}

        for m in hint.key_modules:
            text = str(m)
            # 更鲁棒的写法：非贪婪，正确处理中文括号和混合格式
            match = re.match(r'^([A-Za-z0-9][A-Za-z0-9\-_]*)(?:\s*[\(（][^)）]*[\)）])?', text)
            if match:
                name = match.group(1).strip()[:40]   # 最多40字符，防止括号截断
            else:
                # fallback：取第一个连续字母数字序列
                alt = re.match(r'([A-Za-z0-9\-]+)', text)
                name = alt.group(1)[:40] if alt else text[:20].strip()

            desc = text[:300]
            if name:
                modules[name] = desc

        # 也从 backbone 提取（只取第一个空格前的英文简称）
        if hint.backbone:
            bb_raw = re.split(r'[（(【\u4e00-\u9fff\s]', hint.backbone)[0].strip()
            bb_name = re.sub(r'[^A-Za-z0-9\-]', '', bb_raw).upper()
            if bb_name:
                modules[bb_name] = f"Backbone: {hint.backbone}"

        return modules

    def _extract_code_modules(self, analysis) -> dict:
        """从 UserCodeAnalysis 提取所有实现的模块"""
        modules: dict = {}

        # 从 components 提取
        for comp in getattr(analysis, "components", []):
            class_name = getattr(comp, "class_name", "") or getattr(comp, "name", "")
            key = class_name.upper()
            modules[key] = {
                "name":        class_name,
                "location":    f"{getattr(comp, 'source_file', '')}:{getattr(comp, 'line_number', '?') or '?'}",
                "type":        getattr(comp, "component_type", "module"),
                "description": getattr(comp, "source_file", ""),
            }

        # 从 key_innovations 提取类名
        for inn in getattr(analysis, "key_innovations", []):
            class_matches = re.findall(r'class\s+(\w+)', inn)
            for cls in class_matches:
                if cls.upper() not in modules:
                    modules[cls.upper()] = {
                        "name":        cls,
                        "location":    inn[:100],
                        "type":        "module",
                        "description": inn[:200],
                    }

        return modules

    def _match_arch_to_code(self, arch_name: str, arch_desc: str, code_modules: dict):
        """在代码模块中找到与架构图模块匹配的实现"""
        from shared.models import ModuleMatchResult

        result = ModuleMatchResult(
            arch_module_name=arch_name,
            arch_description=arch_desc[:200],
        )

        arch_upper = arch_name.upper()
        arch_words = set(re.findall(r'[A-Z][a-z]*|[A-Z]+(?=[A-Z]|$)', arch_name))

        best_score = 0.0
        best_code  = None

        for code_key, code_info in code_modules.items():
            score = 0.0
            code_name = code_info["name"]

            if code_key == arch_upper or code_name.upper() == arch_upper:
                score = 100.0
            elif self._is_abbreviation_of(arch_upper, code_name):
                score = 90.0
            elif self._is_abbreviation_of(code_name.upper(), arch_name):
                score = 80.0
            else:
                code_words = set(re.findall(r'[A-Z][a-z]*|[A-Z]+(?=[A-Z]|$)', code_name))
                overlap = len(arch_words & code_words)
                if overlap > 0:
                    score = overlap / max(len(arch_words), 1) * 60
                elif arch_upper in code_key or code_key in arch_upper:
                    score = 40.0

            if score > best_score:
                best_score = score
                best_code  = code_info

        if best_score >= 80:
            result.status        = "verified"
            result.code_name     = best_code["name"]
            result.code_location = best_code["location"]
            result.match_score   = best_score
            result.match_method  = "精确匹配" if best_score == 100 else "缩写扩展匹配"
            result.verification_note = (
                f"架构图中的 {arch_name} 对应代码中的 "
                f"{best_code['name']}（{best_code['location']}），"
                f"匹配度 {best_score:.0f}%"
            )
        elif best_score >= 40:
            result.status        = "partial"
            result.code_name     = best_code["name"] if best_code else ""
            result.code_location = best_code["location"] if best_code else ""
            result.match_score   = best_score
            result.match_method  = "关键词部分匹配"
            result.verification_note = (
                f"架构图的 {arch_name} 与代码中的 "
                f"{best_code['name'] if best_code else '?'} 可能对应，"
                f"但名称差异较大，需人工确认"
            )
        else:
            result.status       = "missing"
            result.match_score  = 0.0
            arch_lower = arch_name.lower()

            # 按模块类型给出个性化 missing 原因分析
            if any(kw in arch_lower for kw in ["pvt", "swin", "resnet", "vit", "convnext"]):
                reason = (
                    "该模块为标准 Backbone，很可能通过 timm 或 torchvision 调用，"
                    "不会有独立类定义"
                )
                suggestion = "在 requirements.txt 或 import 语句中搜索 timm 来确认。"
            elif any(kw in arch_lower for kw in
                     ["diffusion", "ddpm", "ddim", "unet", "denois"]):
                reason = (
                    "扩散模型相关模块可能使用了第三方扩散库（如 denoising-diffusion-pytorch），"
                    "或以函数式调用而非类定义实现"
                )
                suggestion = (
                    "在代码中全局搜索 timestep / time_embed / condition / denoise，"
                    "确认是否有功能等价但命名不同的实现。"
                )
            elif any(kw in arch_lower for kw in
                     ["atcn", "sem", "lem", "cam", "pam", "cbam", "sam"]):
                reason = (
                    "该模块为论文的核心创新模块，未在代码中找到同名类；"
                    "可能：① 代码仓库为早期/简化版本；"
                    "② 功能合并到其他类中实现；"
                    "③ 模块名称在代码中使用了不同命名约定"
                )
                suggestion = "建议在代码中搜索论文中该模块的关键词或功能描述词。"
            else:
                reason = "未找到同名或近名实现，可能是辅助模块或已被重构合并"
                suggestion = (
                    "建议在代码中全局搜索功能性关键词，"
                    "确认是否有功能等价但命名不同的实现。"
                )

            result.verification_note = (
                f"架构图声称的 {arch_name} 模块在代码中未找到对应实现。\n"
                f"分析：{reason}。\n"
                f"建议：{suggestion}"
            )

        return result

    def _is_abbreviation_of(self, abbrev: str, full_name: str) -> bool:
        """判断 abbrev 是否是 full_name 的缩写"""
        if not abbrev or not full_name:
            return False
        initials = "".join(re.findall(r'(?<![a-z])([A-Z])', full_name))
        return abbrev.upper() == initials.upper()

    def _is_mentioned_in_arch(self, code_name: str, hint) -> bool:
        """判断 code_name 是否在架构图描述中被提到"""
        text = (
            hint.structure_hint + " " +
            " ".join(str(m) for m in hint.key_modules)
        ).upper()
        return code_name.upper() in text

    def _generate_conclusion(self, report) -> str:
        """生成验证结论文字"""
        score    = report.consistency_score
        verified = report.verified_count
        missing  = report.missing_count
        total    = report.total_arch_modules

        if score >= 80:
            quality = "高度一致"
            advice  = "代码实现与论文架构图吻合度高，研究可信度强。"
        elif score >= 50:
            quality = "部分一致"
            advice  = "存在若干架构图声称但代码未完整实现的模块，建议重点检查缺失部分。"
        else:
            quality = "一致性较低"
            advice  = "代码与架构图存在较大差异，可能是早期版本代码，或论文存在理想化描述。"

        missing_names = [
            m.arch_module_name
            for m in report.arch_to_code_matches
            if m.status == "missing"
        ]
        code_only_names = [m["name"] for m in report.code_only_modules[:3]]

        conclusion = (
            f"架构一致性：{quality}（{score}%，{verified}/{total} 个模块已验证）。"
            f"{advice}"
        )
        if missing_names:
            conclusion += f"\n⚠️ 未在代码中找到的架构模块：{', '.join(missing_names[:5])}。"
        if code_only_names:
            conclusion += f"\n🔍 代码中存在但架构图未画出的模块：{', '.join(code_only_names)}。"

        return conclusion
