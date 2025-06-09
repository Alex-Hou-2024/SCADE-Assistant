# scadeAgentTools.py
import json
from SCADEAPI import SCADE_Builder

# 全局注册表
registry = {}
builder = SCADE_Builder()


# 装饰器：自动将函数加入 registry
def register(func):
    registry[func.__name__] = func
    return func

# ✅ 注册函数
@register
def load_project_and_model(arguments) -> str:
    project_dir = arguments.get('project_dir')
    project_name = arguments.get('project_name')

    builder.start_jvm()
    builder.init_scade_classes()
    builder.load_project_and_model(project_dir, project_name)
    return "✅ 项目和模型已加载完成"

@register
def switch_to_operator_by_path(arguments) -> str:
    path_str = arguments.get('path_str')
    builder.switch_to_operator_by_path(path_str)
    return f"✅ 已切换到路径: {path_str}"

@register
def create_package(arguments) -> str:
    package_name = arguments.get('package_name')
    builder.create_package(package_name)
    return f"✅ Package {package_name} 创建完成"

@register
def create_operator(arguments) -> str:
    operator_name = arguments.get('operator_name')
    builder.create_operator(operator_name)
    return f"✅ Operator {operator_name} 创建完成"

@register
def create_input(arguments) -> str:
    input_type = arguments.get('type')
    input_name = arguments.get('input_name')
    builder.create_input(input_name, input_type)
    return f"✅ Input {input_name} 创建完成"

@register
def create_output(arguments) -> str:
    output_type = arguments.get('type')
    output_name = arguments.get('output_name')
    builder.create_output(output_name, output_type)
    return f"✅ Output {output_name} 创建完成"

@register
def create_dataFlow(arguments) -> str:
    text = arguments.get('text')
    builder.create_dataFlow(text)
    builder.save_project()
    #builder.shutdown_jvm()
    return "✅ 代码块已解析并生成"

@register
def create_stateMachine(arguments) -> str:
    sm_name = arguments.get('sm_name')
    states = arguments.get('states')
    transitions = arguments.get('transitions')
    builder.create_stateMachine(sm_name, states, transitions)
    builder.save_project()
    # builder.shutdown_jvm()
    return f"✅ StateMachine {sm_name} 创建完成"


tools = [
    {
        "type": "function",
        "function": {
            "name": "load_project_and_model",
            "description": "加载 SCADE 项目及模型。",
            "parameters": {
                "type": "object",
                "properties": {
                    "project_dir": {"type": "string", "description": "SCADE 项目所在的文件夹路径，例如'C:\\example1'"},
                    "project_name": {"type": "string", "description": "SCADE 项目名称（不带扩展名），例如‘example2’。"}
                },
                "required": ["project_dir", "project_name"],
                "additionalProperties": False
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "switch_to_operator_by_path",
            "description": "根据路径切换到指定 Operator。",
            "parameters": {
                "type": "object",
                "properties": {
                    "path_str": {"type": "string", "description": "完整的包/Operator 路径，例如 'Package1::Package2::Operator3/SM1:State1:SM2:State2:SM3:State3:'。"}
                },
                "required": ["path_str"],
                "additionalProperties": False
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_package",
            "description": "在 SCADE 模型中创建一个新 Package。",
            "parameters": {
                "type": "object",
                "properties": {
                    "package_name": {"type": "string", "description": "新建 Package 的名称。"}
                },
                "required": ["package_name"],
                "additionalProperties": False
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_operator",
            "description": "在当前 Package 中创建一个新 Operator。",
            "parameters": {
                "type": "object",
                "properties": {
                    "operator_name": {"type": "string", "description": "新建 Operator 的名称。"}
                },
                "required": ["operator_name"],
                "additionalProperties": False
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_input",
            "description": "在当前 Operator 中添加一个输入端口。",
            "parameters": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "description": "输入变量的数据类型。"},
                    "input_name": {"type": "string", "description": """
                    输入变量名称，输入输出的数据类型只能为："uint8", "uint16", "uint32", "int8", "int16", "int32", "bool", "float32", "float64",
                    或者数组："uint16^5", "uint32^10^20"
                    """}
                },
                "required": ["type", "input_name"],
                "additionalProperties": False
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_output",
            "description": "在当前 Operator 中添加一个输出端口。",
            "parameters": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "description": "输出变量的数据类型。"},
                    "output_name": {"type": "string", "description": """
                    输出变量名称，输入输出的数据类型只能为："uint8", "uint16", "uint32", "int8", "int16", "int32", "bool", "float32", "float64",
                    或者数组："uint16^5", "uint32^10^20"
                    """}
                },
                "required": ["type", "output_name"],
                "additionalProperties": False
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "create_dataFlow",
            "description": "解析给定的表达式块，并在当前 Operator 中生成等式和节点。支持多种运算符，需根据运算类型选择合适的符号。",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": """
---
包含多个表达式（按行分隔）的字符串。每一步运算需要通过临时变量完成，并明确使用下列支持的运算符：
🔹 关系运算符（比较）:  
- `<`, `<=`, `>`, `>=`, `!=`, `<>`, `=`
🔹 算术运算符:  
- `+`, `-`, `*`, `/`, `mod`, `=`
🔹 移位运算符:  
- `<<`（逻辑左移）, `>>`（逻辑右移）
🔹 逻辑运算符:  
- `and`, `or`, `not`, `xor`  
  例如：`_L4 = and(_L1, _L2)`
🔹 位运算符:  
- `land`, `lor`, `lnot`, `lxor`, `<<`, `>>`  
  例如：`_L4 = land(_L1, _L2)`
🔹 特殊运算符:  
- `pre`, `fby`, `cast`
使用时，请严格按照以下格式编写表达式：  
```
_Lz = operator (_Lx, _Ly, ...)
```
✅ 示例：
```
_L1 = Input_01
_L2 = Input_02
_L3 = Input_03
_L4 = + (_L1, _L2, _L3) # 多元算术加法
_L5 = * (_L3, _L4) # 乘法
_L6 = and (_L4, _L5) # 逻辑与
_L7 = land (_L4, _L5) # 位与
_L8 = << (_L4, 1) # 逻辑左移
_L9 = pre (_L5) # 上一周期值
_L10 = fby (_L6, 2, _L7) # _L6延迟2周期值赋值给_L10，延迟期间_L10默认值是_L7
_L11, _L12, _L13 = Operator1 (_L8, _L9, _L10) # 调用除运算符外，其他已创建的Operator
_L6, _L7 = (mapfoldwi 1 Operator2 <<15>> if _L1)(_L2, _L8) # 调用迭代器mapfoldwi，mapfoldwi调用Operator2
Output_01 = _L4
Output_02 = _L5
```
请务必确保每一步只使用支持的运算符，且临时变量（_L1, _L2, ...）用于中间结果存储，只要出现operator的地方一律使用临时变量（_L1, _L2, ...），最终用 Output_xx 赋值输出。

---

                    """}
                },
                "required": ["text"],
                "additionalProperties": False
            }
        }
    },
{
  "type": "function",
  "function": {
    "name": "create_stateMachine",
    "description": "在当前 Operator 中创建一个状态机（StateMachine），包括状态和转换，例如'SM1'。",
    "parameters": {
      "type": "object",
      "properties": {
        "sm_name": {
          "type": "string",
          "description": "状态机的名称。"
        },
        "states": {
          "type": "array",
          "items": {"type": "string"},
          "description": """状态机中包含的所有状态名称，例如：["S1", "S2", "S3", "S4"]。"""
        },
        "transitions": {
          "type": "array",
          "items": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 3,
            "maxItems": 3
          },
          "description": """状态转换关系的列表，每个转换是一个三元组：['起始状态', '目标状态', '转换条件']，'转换条件'为输入名、输出名或者临时变量名，例如：
          [
            ("S1", "S2", "_L1"),
            ("S2", "S3", "_L2"),
            ("S2", "S4", "_L3"),
            ("S3", "S4", "_L4"),
          ]。"""
        }
      },
      "required": ["sm_name", "states", "transitions"],
      "additionalProperties": False
    }
  }
}

]
