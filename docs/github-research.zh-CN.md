# GitHub 同类项目检索记录

检索日期：2026-09-04。

## 结论

截至检索日，没有发现一个可直接满足以下组合要求的成熟开源仓库：

- 中国大陆医院规范名与多个别名的显式映射；
- 区分现名、简称、并行名称、历史名称；
- 每条映射保留来源与时间；
- 对同名医院和院区进行消歧；
- 提供可复用的 Python API、CLI、批量处理和数据校验。

这不是“互联网上绝对不存在”的证明，而是基于 GitHub 仓库搜索、网页
搜索和候选仓库文件树核对后的结论。

## 相关项目

| 项目 | 可利用内容 | 与本项目需求的缺口 |
|---|---|---|
| [dyhuzh/baidu-hospital-crawler](https://github.com/dyhuzh/baidu-hospital-crawler) | 2016 年全国三甲医院网页与 Excel；README 明确指出“一院多名”问题 | 数据未精校，未提供规范名—别名身份映射；最后推送于 2017 年 |
| [46319943/3AHospital](https://github.com/46319943/3AHospital) | 三甲医院名称、地址、经纬度 | 主要解决地理编码，不处理别名、历史名和消歧；最后推送于 2020 年 |
| [wainshine/Medical-Names-Corpus](https://github.com/wainshine/Medical-Names-Corpus) | 大规模医疗机构名称语料 | 是名称语料，不把多个名称聚合为同一医院身份 |
| [hint-lab/chinese-medical-kg](https://github.com/hint-lab/chinese-medical-kg) | 药品、疾病、基因实体标准化和模糊匹配代码 | 标准化对象不是医院，不能直接提供医院别名主数据 |
| [2024 年全国医院名单 5 万条](https://github.com/767172261/List-data-of-hospitals-in-provinces-cities-and-counties-across-the-country-in-2024-50000-items-hospi) | README 声称包含“医院别名”字段 | 仓库文件树只有 README，没有公开数据文件、代码或许可证，无法作为可复用库 |
| [yanshouyu/Chinese_clinical_trials](https://github.com/yanshouyu/Chinese_clinical_trials) | 2018 年 NMPA 登记平台抓取与分析代码 | Python 2、旧版网页端点，没有医院身份归并，无法用于现行平台全量同步 |
| [luyang93/clinical-trials-scrapy](https://github.com/luyang93/clinical-trials-scrapy) | ChiCTR 和 NMPA 抓取代码 | 2020 年已归档，不提供当前医院别名库 |

## 建库原则

本项目把“匹配算法”和“可审计数据”分开。原始医院名单可作为候选发现
来源，但别名关系必须由权威页面逐条确认。模糊匹配只返回候选，不自动
写回规范名；涉及试验中心、合同、付款或监管记录时，应结合省市、地址或
统一社会信用代码人工复核。
