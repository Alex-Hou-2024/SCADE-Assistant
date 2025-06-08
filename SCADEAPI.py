from logging import getLevelName
import jpype, json
import uuid, os, re
from jpype.types import JInt

class SCADE_Builder:
    def __init__(self):
        #
        self.URI = None
        self.ResourceSetImpl = None
        self.ScadeModelReader = None
        self.ScadeModelWriter = None
        self.OperatorKind = None
        self.ScadePackage = None
        self.theScadeFactory = None
        self.CodegenPragmasPackage = None
        self.theCodegenPragmasFactory = None
        self.EditorPragmasPackage = None
        self.theEditorPragmasFactory = None
        self.EditorPragmasUtil = None
        self.EcoreUtil = None

        self.baseURI = None
        self.projectURI = None
        self.resourceSet = None
        self.project = None
        self.mainModel = None

        self.Operator_Pragma = None
        self.Operator_Diagram = None

        # 当前工作目录指针
        self.current_package = None
        self.current_operator = None
        self.current_canvas = None
        self.current_full_dir = "Package1::Operator1/"

        # _Lx临时变量相关
        self.lx_to_ge = {}
        self.lx_to_ge[self.current_full_dir] = {}


    def start_jvm(self,
                  jvm_path=None,
                  scade_lib_path=None,
                  current_dir=None):
        """
        启动 JVM，并设置 classpath。
        可传入参数自定义路径，也可使用默认路径。
        """
        if jpype.isJVMStarted():
            print("⚠️ JVM 已启动，跳过")
            return

        # 默认值（可改为类属性或读取配置）
        jvm_path = jvm_path or r"C:\Program Files\Java\jdk-11.0.2\bin\server\jvm.dll"
        scade_lib_path = scade_lib_path or r"C:\Program Files\ANSYS Inc\v202\SCADE\contrib\lib\*"
        current_dir = current_dir or os.getcwd()

        jpype.startJVM(jvm_path, classpath=[scade_lib_path, current_dir])
        self.jvm_started = True
        print("✅ JVM 启动成功")


    def shutdown_jvm(self):
        jpype.shutdownJVM()
        print("✅ JVM 已关闭")


    def init_scade_classes(self):
        self.URI = jpype.JClass("org.eclipse.emf.common.util.URI")
        self.ResourceSetImpl = jpype.JClass("org.eclipse.emf.ecore.resource.impl.ResourceSetImpl")

        self.ScadeModelReader = jpype.JClass("com.esterel.scade.api.util.ScadeModelReader")
        self.ScadeModelWriter = jpype.JClass("com.esterel.scade.api.util.ScadeModelWriter")

        self.OperatorKind = jpype.JClass("com.esterel.scade.api.OperatorKind")

        self.ScadePackage = jpype.JClass("com.esterel.scade.api.ScadePackage")
        self.theScadeFactory = self.ScadePackage.eINSTANCE.getScadeFactory()

        self.CodegenPragmasPackage = jpype.JClass("com.esterel.scade.api.pragmas.codegen.CodegenPragmasPackage")
        self.theCodegenPragmasFactory = self.CodegenPragmasPackage.eINSTANCE.getCodegenPragmasFactory()

        self.EditorPragmasPackage = jpype.JClass("com.esterel.scade.api.pragmas.editor.EditorPragmasPackage")
        self.theEditorPragmasFactory = self.EditorPragmasPackage.eINSTANCE.getEditorPragmasFactory()

        self.EditorPragmasUtil = jpype.JClass("com.esterel.scade.api.pragmas.editor.util.EditorPragmasUtil")
        self.EcoreUtil = jpype.JClass("org.eclipse.emf.ecore.util.EcoreUtil")


    def init_project_and_model(self, project_dir: str, project_name: str):
        self.baseURI = self.URI.createFileURI(project_dir)
        self.projectURI = self.baseURI.appendSegment(f"{project_name}.etp")
        self.resourceSet = self.ResourceSetImpl()
        self.project = self.ScadeModelWriter.createEmptyScadeProject(self.projectURI, self.resourceSet)
        self.mainModel = self.ScadeModelWriter.loadModel(self.projectURI, self.resourceSet)
        print("✅ 项目和模型初始化完成")


    def load_project_and_model(self, project_dir: str, project_name: str):
        project_file = os.path.join(project_dir, f"{project_name}.etp")
        if not os.path.exists(project_file):
            print(f"❌ 项目文件不存在: {project_file}")
            return

        self.baseURI = self.URI.createFileURI(project_dir)
        self.projectURI = self.baseURI.appendSegment(f"{project_name}.etp")
        self.resourceSet = self.ResourceSetImpl()

        # 尝试只加载模型，跳过 getProject
        self.mainModel = self.ScadeModelReader.loadModel(self.projectURI, self.resourceSet)
        if self.mainModel is None:
            print("❌ loadModel() 也失败了")
        else:
            print("✅ 只通过 loadModel() 加载模型成功")

        self.project = self.ScadeModelReader.getProject(self.projectURI, self.resourceSet)
        self.mainModel = self.ScadeModelReader.loadModel(self.projectURI, self.resourceSet)
        print("✅ 项目和模型初始化完成")


    def find_operator(self, op_name: str):
        if self.current_package is None:
            print("❌ 当前未选中 Package")
            return None
        declarations = self.current_package.getDeclarations()
        for decl in declarations:
            if decl.eClass().getName() == "Operator":
                if decl.getName() == op_name:
                    print(f"✅ 找到 Operator: {op_name}")
                    return decl
        print(f"❌ 未找到 Operator: {op_name}")
        return None


    def switch_to_operator_by_path(self, path_str: str):
        """
        递归切换到完整路径中指定的 Package、Operator 以及 Operator 内部的 canvas（状态机/状态等）。
        - 例如:
            "Package1::Package2::Operator3/SM1:State1:SM2:State2:SM3:State3:"
            1️⃣ :: 之前为包名
            2️⃣ / 之前是 Operator
            3️⃣ / 之后以 : 分隔的为 Operator 内部 canvas 路径，可递归处理
        """
        self.current_full_dir = path_str.strip()
        self.lx_to_ge[self.current_full_dir] = {}
        if not path_str.strip():
            print("❌ 空路径")
            return None

        # 拆分为 "Package::...::Operator/内部路径"
        if "/" in path_str:
            package_op_part, canvas_part = path_str.split("/", 1)
        else:
            package_op_part, canvas_part = path_str, None

        # 处理 package 和 operator
        segments = [seg for seg in package_op_part.strip().split("::") if seg]
        if len(segments) < 1:
            print("❌ 路径中缺少包名")
            return None

        # 根包
        root_pkg_name = segments[0]
        current = None
        for obj in self.mainModel.getDeclarations():
            if hasattr(obj, "getName") and obj.eClass().getName() == "Package" and obj.getName() == root_pkg_name:
                current = obj
                break
        if current is None:
            print(f"❌ 未找到根 Package: {root_pkg_name}")
            return None

        # 递归进入中间包
        for pkg_name in segments[1:-1]:
            next_pkg = None
            for decl in current.getDeclarations():
                if decl.eClass().getName() == "Package" and decl.getName() == pkg_name:
                    next_pkg = decl
                    break
            if next_pkg is None:
                print(f"❌ 未找到子包: {pkg_name}")
                return None
            current = next_pkg

        # Operator
        operator_name = segments[-1]
        operator_obj = None
        for op in current.getOperators():
            if op.getName() == operator_name:
                operator_obj = op
                break
        if operator_obj is None:
            print(f"❌ 未找到 Operator: {operator_name}")
            return None

        # 更新当前指针
        self.current_package = current
        self.current_operator = operator_obj
        self.current_canvas = operator_obj
        print(f"✅ 成功切换到 Operator: {self.current_operator.getName()}")

        # 如果没有 canvas 部分，直接返回 Operator
        if not canvas_part:
            return self.current_operator

        # 递归进入 Operator 内部 canvas（状态机、状态…）
        canvas_segments = [seg for seg in canvas_part.strip(":").split(":") if seg]
        current_obj = self.current_operator

        for idx, seg in enumerate(canvas_segments):
            # 检查当前对象是否有 getData() 且 data 下有 getStateMachines()
            if hasattr(current_obj, "getData") and current_obj.getData() is not None:
                # ⚠️ 假设 current_operator 已经是一个 Operator 或者 State，且已经加载到 Python 中
                flows = current_obj.getData()  # EList<Flow>
                for flow in flows:
                    # 检查 flow 的类型
                    eclass_name = flow.eClass().getName()
                    if eclass_name == "StateMachine":
                        print(f"✅ 找到 StateMachine: {flow.getName()}")
                        if flow.getName() == seg:
                            print(f"✅ 进入 StateMachine: {seg}")
                            current_obj = flow
                            break
                    elif eclass_name == "WhenBlock":
                        print(f"🔹 找到 WhenBlock: {flow.getName()}")
                    elif eclass_name == "IfBlock":
                        print(f"🔹 找到 IfBlock: {flow.getName()}")
                    else:
                        print(f"🔸 其他 Flow: {eclass_name}")
                continue

            # 如果没有状态机匹配，检查是否为状态
            if hasattr(current_obj, "getStates"):
                states = current_obj.getStates()
                for st in states:
                    if st.getName() == seg:
                        current_obj = st
                        print(f"✅ 进入 State: {seg}")
                        self.current_canvas = current_obj
                        break
                continue  # 继续处理下一个段

            # 如果都没找到
            print(f"❌ 当前对象下未找到: {seg}")
            return None

        print(f"✅ 完成全路径切换: {path_str}")
        return self.current_canvas


    def find_typeObject(self, name: str):
        allContents = self.EcoreUtil.getAllContents(self.mainModel, True)
        while allContents.hasNext():
            obj = allContents.next()
            # 只取类名叫 "Type" 且有 getName 方法的对象
            if hasattr(obj, "getName") and obj.eClass().getName() == "Type" :
                if obj.getName() == name:
                    return obj
        return None


    def generate_oid(self, prefix="!ed"):
        return f"{prefix}/{str(uuid.uuid4()).upper().replace('-', '/')}"


    def create_package(self, package_name: str):
        uriPackage = self.baseURI.appendSegment(f"{package_name}.xscade")
        resourcePackage = self.resourceSet.createResource(uriPackage)
        Package = self.theScadeFactory.createPackage()
        Package.setName(package_name)
        self.mainModel.getPackages().add(Package)
        resourcePackage.getContents().add(Package)
        # 包 Pragma
        Package_Pragma = self.theEditorPragmasFactory.createPackage()
        Package_Pragma.setOid(self.generate_oid())
        Package_Pragma.getComments().add(f"This is {package_name}.")
        Package_Pragma.getComments().add("This package has been generated through the SCADE Eclipse/EMF API.")
        Package.getPragmas().add(Package_Pragma)
        print(f"✅ Package {package_name} 创建完成")
        self.current_package = Package
        return Package


    def create_type_from_string(self, type_name: str):
        """
        将 Type1^3^2 转换成多维 Table 嵌套类型。
        - 最里层：NamedType(Type1)
        - 外层：Table（size=3）, Table（size=2）
        """
        segments = type_name.split("^")
        base_type_name = segments[0]
        sizes = segments[1:]  # ["3", "2"]

        # 找到最里层类型（Type1）
        base_type = self.find_typeObject(base_type_name)
        current_type = self.theScadeFactory.createNamedType()
        current_type.setType(base_type)

        # 逐层外包裹 Table
        for size in sizes:
            table_type = self.theScadeFactory.createTable()
            table_type.setType(current_type)  # 元素类型
            size_const = self.theScadeFactory.createConstValue()
            size_const.setValue(size)
            table_type.setSize(size_const)

            current_type = table_type  # 外包裹一层，继续

        return current_type


    def create_const_value_recursive(self, value, type_obj):
        """
        递归创建 ConstValue, DataStructOp, DataArrayOp (嵌套支持).
        只有在 type_obj 是数组类型（如 Type1^3, Type1^3^2）时，才创建 Table。
        """
        if isinstance(value, str):
            try:
                parsed_value = json.loads(value)
            except json.JSONDecodeError:
                parsed_value = value  # 不是 JSON，直接使用
        else:
            parsed_value = value

        # 基础值
        if isinstance(parsed_value, (str, int, float, bool)):
            const_val = self.theScadeFactory.createConstValue()
            if isinstance(parsed_value, bool):
                const_val.setValue(str(parsed_value).lower())
            else:
                const_val.setValue(str(parsed_value))
            return const_val

        # 结构体
        if isinstance(parsed_value, dict):
            data_struct_op = self.theScadeFactory.createDataStructOp()
            for label, sub_val in parsed_value.items():
                labelled_expr = self.theScadeFactory.createLabelledExpression()
                labelled_expr.setLabel(label)
                # 递归生成 flow
                flow_val = self.create_const_value_recursive(sub_val, None)
                labelled_expr.setFlow(flow_val)
                data_struct_op.getData().add(labelled_expr)
            return data_struct_op

        # 数组
        if isinstance(parsed_value, list):
            data_array_op = self.theScadeFactory.createDataArrayOp()

            # ⚠️ 只有在 type_obj 是数组类型，才创建 Table
            if type_obj and type_obj.eClass().getName() == "Table":
                table = self.theScadeFactory.createTable()
                table.setDefinedType(type_obj.getDefinedType())

                array_size = self.theScadeFactory.createConstValue()
                array_size.setValue(str(len(parsed_value)))
                table.setSize(array_size)

                data_array_op.setTable(table)

            # 递归生成 data 元素
            for idx, item in enumerate(parsed_value):
                # 如果 type_obj 是 Table，传入元素类型（元素Type1）
                element_type = type_obj.getDefinedType() if (
                            type_obj and type_obj.eClass().getName() == "Table") else None
                item_val = self.create_const_value_recursive(item, element_type)
                data_array_op.getData().add(idx, item_val)

            return data_array_op

        # fallback
        const_val = self.theScadeFactory.createConstValue()
        const_val.setValue(str(parsed_value))
        return const_val


    def create_constant(self, constant_name: str, type_name: str, value: str):
        if self.current_package is None:
            print("❌ 当前未选择 Package")
            return None

        # 名称重复检查
        for existing_constant in self.current_package.getConstants():
            if existing_constant.getName() == constant_name:
                print(f"⚠️ 输入名 '{constant_name}' 已存在于 Package '{self.current_package.getName()}' 中，拒绝添加。")
                return existing_constant

        Constant = self.theScadeFactory.createConstant()
        Constant.setName(constant_name)

        # 解析 type_name，生成完整的 Table/Type 层次结构
        type_obj = self.create_type_from_string(type_name)
        Constant.setType(type_obj)

        # 创建常量值
        constant_value = self.create_const_value_recursive(value, type_obj)
        Constant.setValue(constant_value)

        # 添加到当前包
        self.current_package.getDeclarations().add(Constant)

        # codegen pragma
        Constant_KCGPragma = self.theCodegenPragmasFactory.createPragma()
        Constant_KCGPragma.setData(f"C:name {constant_name}")
        Constant.getPragmas().add(Constant_KCGPragma)

        print(f"✅ Constant '{constant_name}' 创建完成")
        return Constant


    def create_sensor(self, sensor_name: str, type_name: str):
        if self.current_package is None:
            print("❌ 当前未选择 Package")
            return None

        # 名称重复检查
        for existing_sensor in self.current_package.getSensors():
            if existing_sensor.getName() == sensor_name:
                print(f"⚠️ 输入名 '{sensor_name}' 已存在于 Package '{self.current_package.getName()}' 中，拒绝添加。")
                return existing_sensor

        Sensor = self.theScadeFactory.createSensor()
        Sensor.setName(sensor_name)

        # ✅ 关键：使用 create_type_from_string 生成完整 Type 层次
        type_obj = self.create_type_from_string(type_name)
        Sensor.setType(type_obj)

        # 添加到当前包
        self.current_package.getDeclarations().add(Sensor)

        # codegen pragma
        Sensor_KCGPragma = self.theCodegenPragmasFactory.createPragma()
        Sensor_KCGPragma.setData(f"C:name {sensor_name}")
        Sensor.getPragmas().add(Sensor_KCGPragma)

        print(f"✅ Constant '{sensor_name}' 创建完成")
        return Sensor


    def create_operator(self, operator_name: str):
        if self.current_package is None:
            print("❌ 当前未选择 Package")
            return None

        # 名称重复检查
        for existing_operator in self.current_package.getOperators():
            if existing_operator.getName() == operator_name:
                print(f"⚠️ 输入名 '{operator_name}' 已存在于 Package '{self.current_package.getName()}' 中，拒绝添加。")
                return existing_operator

        Operator = self.theScadeFactory.createOperator()
        Operator.setName(operator_name)
        Operator.setKind(self.OperatorKind.NODE_LITERAL)
        self.current_package.getDeclarations().add(Operator)
        # codegen pragma
        Operator_KCGPragma = self.theCodegenPragmasFactory.createPragma()
        Operator_KCGPragma.setData(f"C:name {operator_name}")
        Operator.getPragmas().add(Operator_KCGPragma)
        print(f"✅ Operator {operator_name} 创建完成")
        self.current_operator = Operator
        self.current_canvas = Operator
        return Operator


    def create_input(self, input_name: str, type_name: str):
        if self.current_operator is None:
            print("❌ 当前未选择 Operator")
            return None

        # 名称重复检查
        for existing_input in self.current_operator.getInputs():
            if existing_input.getName() == input_name:
                print(f"⚠️ 输入名 '{input_name}' 已存在于 Operator '{self.current_operator.getName()}' 中，拒绝添加。")
                return existing_input

        Input = self.theScadeFactory.createVariable()
        Input.setName(input_name)

        # 解析 type_name，生成完整的 Table/Type 层次结构
        type_obj = self.create_type_from_string(type_name)
        Input.setType(type_obj)

        self.current_operator.getInputs().add(Input)
        return Input


    def create_output(self, output_name: str, type_name: str):
        if self.current_operator is None:
            print("❌ 当前未选择 Operator")
            return None

        # 名称重复检查
        for existing_output in self.current_operator.getOutputs():
            if existing_output.getName() == output_name:
                print(f"⚠️ 输入名 '{output_name}' 已存在于 Operator '{self.current_operator.getName()}' 中，拒绝添加。")
                return existing_output

        Output = self.theScadeFactory.createVariable()
        Output.setName(output_name)

        # 解析 type_name，生成完整的 Table/Type 层次结构
        type_obj = self.create_type_from_string(type_name)
        Output.setType(type_obj)

        self.current_operator.getOutputs().add(Output)
        return Output


    # 根据字符串创建
    def create_local(self, local_name: str, type_name: str):
        if self.current_canvas is None:
            print("❌ 当前未选择 Operator")
            return None

        # 名称重复检查
        for existing_local in self.current_canvas.getLocals():
            if existing_local.getName() == local_name:
                print(f"⚠️ 输入名 '{local_name}' 已存在于 Canvas '{self.current_canvas.getName()}' 中，拒绝添加。")
                return existing_local

        Local = self.theScadeFactory.createVariable()
        Local.setName(local_name)

        # 解析 type_name，生成完整的 Table/Type 层次结构
        type_obj = self.create_type_from_string(type_name)
        Local.setType(type_obj)

        self.current_canvas.getLocals().add(Local)
        return Local


    # 根据类型创建，这里的type不是string
    def create_local_E(self, type_obj, local_name="Local1"):
        if self.current_canvas is None:
            print("❌ 当前未选择 Operator")
            return None

        # 名称重复检查
        for existing_local in self.current_canvas.getLocals():
            if existing_local.getName() == local_name:
                print(f"⚠️ 输入名 '{local_name}' 已存在于 Canvas '{self.current_canvas.getName()}' 中，拒绝添加。")
                return existing_local

            # 使用 clone_type() 深拷贝，避免“引用转移”
        cloned_type = self.clone_type(type_obj)

        Local = self.theScadeFactory.createVariable()
        Local.setName(local_name)
        Local.setType(cloned_type)
        self.current_canvas.getLocals().add(Local)
        return Local


    def clone_type(self, type_obj):
        """
        深度克隆 Type（NamedType、Table），包括 size 的深拷贝。
        """
        type_name = type_obj.eClass().getName()
        if type_name == "NamedType":
            new_named_type = self.theScadeFactory.createNamedType()
            new_named_type.setType(type_obj.getType())  # 这里可直接引用
            return new_named_type
        elif type_name == "Table":
            new_table = self.theScadeFactory.createTable()
            # 深拷贝 size
            orig_size = type_obj.getSize()
            new_size = self.theScadeFactory.createConstValue()
            new_size.setValue(orig_size.getValue())  # 只复制 value
            new_table.setSize(new_size)
            # 递归克隆子类型
            new_table.setType(self.clone_type(type_obj.getType()))
            return new_table
        else:
            print(f"⚠️ 不支持克隆的 Type 类型: {type_name}")
            return type_obj


    def save_project(self):
        self.ScadeModelWriter.updateProjectWithModelFiles(self.project)
        self.ScadeModelWriter.saveAll(self.project, None)
        print("✅ 项目保存完成")


    def determine_var_kind(self, var_name):
        """
        判断给定变量名字是 Input、Local，还是不存在。
        返回 'Input' / 'Local' / 'NotFound'
        """
        if self.current_operator is None:
            print("❌ 当前未选择 Operator")
            return None

        # 查找输入
        for var in self.current_operator.getInputs():
            if var.getName() == var_name:
                return "Input", var

        # 查找局部变量
        for var in self.current_operator.getLocals():
            if var.getName() == var_name:
                return "Local", var

        # 查找局部变量
        for var in self.current_canvas.getLocals():
            if var.getName() == var_name:
                return "Local", var

        # 查找局部变量
        for var in self.current_operator.getOutputs():
            if var.getName() == var_name:
                return "Output", var

        # 都没找到
        return "NotFound", None


    # 用于创建和输入关联的等式
    def create_input_equation_E(self, Input, _Lx):
        Equation = self.theScadeFactory.createEquation()
        Equation.getLefts().add(_Lx)
        rightExpr = self.theScadeFactory.createIdExpression()
        rightExpr.setPath(Input)
        Equation.setRight(rightExpr)
        self.current_canvas.getData().add(Equation)
        self.EditorPragmasUtil.setOid(Equation, self.generate_oid())
        return Equation


    def create_EquationGE(self, Equation, varName: str, x: int = 1000, y: int = 1000, width: int = 1000, height: int = 1000):
        GE = self.theEditorPragmasFactory.createEquationGE()
        GE.setEquation(Equation)
        pos = self.theEditorPragmasFactory.createPoint()
        pos.setX(x)
        pos.setY(y)
        GE.setPosition(pos)
        size = self.theEditorPragmasFactory.createSize()
        size.setWidth(width)
        size.setHeight(height)
        GE.setSize(size)
        self.Operator_Diagram.getPresentationElements().add(GE)
        self.lx_to_ge[self.current_full_dir][varName] = GE
        return GE


    def create_Edge(self, GE1, GE2, idx1, idx2):
        Edge = self.theEditorPragmasFactory.createEdge()
        Edge.setSrcEquation(GE1)
        Edge.setDstEquation(GE2)
        Edge.setLeftVarIndex(idx1)
        Edge.setRightExprIndex(idx2)
        pt1 = self.theEditorPragmasFactory.createPoint()
        pt1.setX(1000)
        pt1.setY(1000)
        pt2 = self.theEditorPragmasFactory.createPoint()
        pt2.setX(1000)
        pt2.setY(1000)
        Edge.getPositions().add(pt1)
        Edge.getPositions().add(pt2)
        self.Operator_Diagram.getPresentationElements().add(Edge)
        return Edge


    def create_StateMachineGE(self, StateMachine, varName: str, x: int = 1000, y: int = 1000, width: int = 20000, height: int = 20000):
        GE = self.theEditorPragmasFactory.createStateMachineGE()
        GE.setStateMachine(StateMachine)
        pos = self.theEditorPragmasFactory.createPoint()
        pos.setX(x)
        pos.setY(y)
        GE.setPosition(pos)
        size = self.theEditorPragmasFactory.createSize()
        size.setWidth(width)
        size.setHeight(height)
        GE.setSize(size)
        self.Operator_Diagram.getPresentationElements().add(GE)
        #self.lx_to_ge[self.current_full_dir][varName] = GE
        return GE


    def create_StateGE(self, State, varName: str, x: int = 1000, y: int = 1000, width: int = 2000, height: int = 2000):
        GE = self.theEditorPragmasFactory.createStateGE()
        GE.setState(State)
        pos = self.theEditorPragmasFactory.createPoint()
        pos.setX(x)
        pos.setY(y)
        GE.setPosition(pos)
        size = self.theEditorPragmasFactory.createSize()
        size.setWidth(width)
        size.setHeight(height)
        GE.setSize(size)
        self.Operator_Diagram.getPresentationElements().add(GE)
        #self.lx_to_ge[self.current_full_dir][varName] = GE
        return GE


    def create_TransitionGE(self, Transition, varName: str, x1: int = 1000, y1: int = 1000, x2: int = 1000, y2: int = 1000):
        GE = self.theEditorPragmasFactory.createTransitionGE()
        GE.setPolyline(True)
        GE.setTransition(Transition)
        pt1 = self.theEditorPragmasFactory.createPoint()
        pt1.setX(x1)
        pt1.setY(y1)
        pt2 = self.theEditorPragmasFactory.createPoint()
        pt2.setX(x2)
        pt2.setY(y2)
        pt3 = self.theEditorPragmasFactory.createPoint()
        pt3.setX(x1+100)
        pt3.setY(y1+100)
        pt4 = self.theEditorPragmasFactory.createPoint()
        pt4.setX(x2+100)
        pt4.setY(y2+100)
        GE.getPositions().add(pt1)
        GE.getPositions().add(pt2)
        GE.getPositions().add(pt3)
        GE.getPositions().add(pt4)
        self.Operator_Diagram.getPresentationElements().add(GE)
        #self.lx_to_ge[self.current_full_dir][varName] = GE
        return GE

        
    # 用于创建和输入关联的等式
    def create_input_equation(self, input: str, output: str):
        _L1 = None
        var_kind_i, var_i = self.determine_var_kind(input)
        # 建立等式：Input1 = _L1
        if var_kind_i == "Input":
            var_kind_o, var_o = self.determine_var_kind(output)

            # 正常情况：Input1 = _L1
            if var_kind_o == "Local":
                print(f"🟡 {var_o.getName()}这是一个局部变量")
                _L1 = var_o
            # Input1 = _L1 但是 _L1未定义
            else:
                print(f"🟡 未找到变量{output}, 开始创建")
                _L1 = self.create_local_E(var_i.getType(), output)

            Equation = self.create_input_equation_E(var_i, _L1)
            self.create_EquationGE(Equation, output, 1000, 1000, 500, 500)

        # Input1未定义
        else:
            print(f"⚠️ 未找到输出{var_i.getName()}")


    def create_output_equation(self, input: str, output: str):
        _L2 = None
        var_kind, var = self.determine_var_kind(input)

        # 输出直连输入的情况：Output1 = Input1
        # 此时调用get_input_local_equation增加_L2为中间变量并建立_L2 = Input1的等式
        if var_kind == "Input":
            print(f"⚠️ {var.getName()}这是一个输入变量，不能直接用于输出")

        # 正常情况：Output1 = _L2
        elif var_kind == "Local":
            print(f"🟡 {var.getName()}这是一个局部变量")
            _L2 = var

        # Output1 = _L2 但是 _L2未定义
        else:
            print(f"⚠️ 未找到变量{var.getName()}")

        var_kind, var = self.determine_var_kind(output)
        # 建立等式：Output1 = _L2
        if var_kind == "Output":
            Equation = self.theScadeFactory.createEquation()
            Equation.getLefts().add(var)
            rightExpr = self.theScadeFactory.createIdExpression()
            rightExpr.setPath(_L2)
            Equation.setRight(rightExpr)
            self.current_canvas.getData().add(Equation)
            self.EditorPragmasUtil.setOid(Equation, self.generate_oid())

            GE1 = self.lx_to_ge[self.current_full_dir][input] 
            GE2 = self.create_EquationGE(Equation, output, 10000, 1000, 500, 500)
            # Edge
            self.create_Edge(GE1, GE2, 1, 1)

        # Output1未定义
        else:
            print(f"⚠️ 未找到输出{var.getName()}")


    def create_buildInOperator_equation(self, expr):
        operator = expr['operator']
        print(f"🔵 Processing Build-in Operator: {operator}")
        Equation = self.theScadeFactory.createEquation()
        opObj = None
        outType = None # 类型推理
        GE2 = None

        if operator in {"+", "*", "and", "or", "xor", "land", "lor"}:
            opObj = self.theScadeFactory.createNAryOp()
            opObj.setOperator(operator)
        elif operator in {"not", "lnot"}:
            opObj = self.theScadeFactory.createUnaryOp()
            opObj.setOperator(operator)
            # 添加一个操作数
            # ... 你的处理逻辑 ...
        elif operator in {"-", "/", "mod", "&lt;", "&lt;=", "&gt;", "&gt;=", "&lt;&gt;", "=", "lxor", "lsl", "lsr"}:
            opObj = self.theScadeFactory.createBinaryOp()
            opObj.setOperator(operator)
            # 添加两个操作数
            # ... 你的处理逻辑 ...
        elif operator in {"1"}:
            opObj = self.theScadeFactory.createNumericCastOp()
            opObj.setOperator(operator)
            # ... 你的处理逻辑 ...
        elif operator in {"pre"}:
            opObj = self.theScadeFactory.createPreOp()
            opObj.setOperator(operator)
        elif operator in {"fby"}:
            opObj = self.theScadeFactory.createFbyOp()
            opObj.setOperator(operator)
            # 添加多个操作数
            # ... 你的处理逻辑 ...
            
        for input in expr['inputs']:
            var_kind, var = self.determine_var_kind(input)
            if var_kind == "Input":
                print(f"⚠️ {var.getName()}是一个输入变量，buildInOperator不能直接读取，发生错误！")

            elif var_kind == "Local":
                print(f"🟡 {var.getName()}是一个用于读取的局部变量")
                _L1 = var
                outType = _L1.getType()
                rightExpr = self.theScadeFactory.createIdExpression()
                rightExpr.setPath(_L1)
                opObj.getOperands().add(rightExpr)

            else:
                print(f"⚠️ 未找到输入变量{var.getName()}，发生错误！")

        for output in expr['outputs']:
            var_kind, var = self.determine_var_kind(output)
            if var_kind == "Output":
                print(f"⚠️ 对输出{output}计算后赋值，发生错误！")
                # TODO 例如：Output_01 = / (_L2, _L3)的情况处理
                #_L2 = self.create_local_E(outType, out)
                #self.create_output_equation("_L2", output)

            elif var_kind == "Local":
                print(f"⚠️ 局部变量{output}被再次写入，发生错误！")

            else:
                print(f"🟡 未找到变量{output}, 开始创建")
                _L2 = self.create_local_E(outType, output)
                Equation.getLefts().add(_L2)
                # GE2 Buildin的operator一般只有一个输出
                GE2 = self.create_EquationGE(Equation, output, 5000, 1000, 800, 700)

        Equation.setRight(opObj)
        self.current_canvas.getData().add(Equation)
        self.EditorPragmasUtil.setOid(Equation, self.generate_oid())

        for index, input in enumerate(expr['inputs']):
            GE1 = self.lx_to_ge[self.current_full_dir][input]
            self.create_Edge(GE1, GE2, 1, index + 1)


    def create_operator_equation(self, expr):
        operator = expr['operator']
        print(f"🔵 Processing Operator: {operator}")
        GE2 = None

        Equation = self.theScadeFactory.createEquation()
        calledOp = self.find_operator(operator)
        opObj = self.theScadeFactory.createOpCall()
        opObj.setOperator(calledOp)
        opObj.setName("calledOp")
        rightExpr = self.theScadeFactory.createCallExpression()
        rightExpr.setOperator(opObj)

        for input in expr['inputs']:
            var_kind, var = self.determine_var_kind(input)
            if var_kind == "Input":
                print(f"⚠️ {var.getName()}是一个输入变量，buildInOperator不能直接读取，发生错误！")

            elif var_kind == "Local":
                print(f"🟡 {var.getName()}是一个用于读取的局部变量")
                idExpr = self.theScadeFactory.createIdExpression()
                idExpr.setPath(var)
                rightExpr.getCallParameters().add(idExpr)

            else:
                print(f"⚠️ 未找到输入变量{var.getName()}，发生错误！")

        for index, output in enumerate(expr['outputs']):
            var_kind, var = self.determine_var_kind(output)
            if var_kind == "Output":
                print(f"⚠️ 对输出{output}计算后赋值，发生错误！")
                # TODO 例如：Output_01 = / (_L2, _L3)的情况处理
                # _L2 = self.create_local_E(outType, out)
                # self.create_output_equation("_L2", output)

            elif var_kind == "Local":
                print(f"⚠️ 局部变量{output}被再次写入，发生错误！")

            else:
                print(f"🟡 未找到变量{output}, 开始创建")
                outType = self.get_output_port_data_type(calledOp, index)
                _L2 = self.create_local_E(outType, output)
                Equation.getLefts().add(_L2)

        for index, output in enumerate(expr['outputs']):
            # GE2
            if index == 0:
                GE2 = self.create_EquationGE(Equation, output, 5000, 1000, 1500, 2600)
            else:
                self.lx_to_ge[self.current_full_dir][output] = GE2

        Equation.setRight(rightExpr)
        self.current_canvas.getData().add(Equation)
        self.EditorPragmasUtil.setOid(Equation, self.generate_oid())

        for index, input in enumerate(expr['inputs']):
            GE1 = self.lx_to_ge[self.current_full_dir][input]
            self.create_Edge(GE1, GE2, 1, index + 1)


    def create_mapfoldwi_equation(self, expr):
        operator = expr['operator']
        subOperator = expr['subOperator']
        accumulators = expr['accumulators']
        size = expr['size']
        cond = expr['condition']
        print(f"🔵 Processing Operator: {operator} and {subOperator}")
        GE2 = None

        Equation = self.theScadeFactory.createEquation()
        calledOp = self.find_operator(subOperator)

        input_count = len(calledOp.getInputs())
        output_count = len(calledOp.getOutputs())
        if input_count != len(expr['inputs']) + 1 or output_count != len(expr['outputs']) + 1:
            print(f"⚠️ 输入数量不一致或输出数量不一致！")
            print(f"    subOperator 输入数: {input_count}")
            print(f"    表达式输入数: {len(expr['inputs'])}")
            print(f"    subOperator 输出数: {output_count}")
            print(f"    表达式输出数: {len(expr['outputs'])}")
            print(f"⚠️ 是一个输入变量，buildInOperator不能直接读取，发生错误！")
            return

        opObj = self.theScadeFactory.createOpCall()
        opObj.setOperator(calledOp)
        opObj.setName("calledOp")

        iteratorOp = self.theScadeFactory.createPartialIteratorOp()
        iteratorOp.setName("abc")
        iteratorOp.setIterator("mapfoldwi")
        iteratorOp.setAccumulatorCount(accumulators)
        iteratorOp.setOperator(opObj)

        # size设定
        contvalue = self.theScadeFactory.createConstValue()
        contvalue.setValue(size)
        iteratorOp.setSize(contvalue)

        # default输入条件设定 数量为被调operator输出数目-accumulators-1
        list = self.theScadeFactory.createListExpression()
        for idx in range(output_count - int(accumulators) - 1):
            idExpr = self.theScadeFactory.createIdExpression()
            # idExpr.setPath(var) 暂时不考虑自动设置，先手动设置
            list.getItems().add(idExpr)
        iteratorOp.setDefault(list)

        # if条件设定
        var_kind, var = self.determine_var_kind(cond)
        if var_kind == "Input":
            print(f"⚠️ {var.getName()}是一个输入变量，buildInOperator不能直接读取，发生错误！")
            return
        elif var_kind == "Local":
            print(f"🟡 {var.getName()}是一个用于读取的局部变量")
            idExpr = self.theScadeFactory.createIdExpression()
            idExpr.setPath(var)
            iteratorOp.setIf(idExpr)
        else:
            print(f"⚠️ 未找到输入变量{var.getName()}，发生错误！")
            return

        callExpression = self.theScadeFactory.createCallExpression()
        callExpression.setOperator(iteratorOp)

        for input in expr['inputs']:
            var_kind, var = self.determine_var_kind(input)
            if var_kind == "Input":
                print(f"⚠️ {var.getName()}是一个输入变量，buildInOperator不能直接读取，发生错误！")
                return

            elif var_kind == "Local":
                print(f"🟡 {var.getName()}是一个用于读取的局部变量")
                idExpr = self.theScadeFactory.createIdExpression()
                idExpr.setPath(var)
                callExpression.getCallParameters().add(idExpr)

            else:
                print(f"⚠️ 未找到输入变量{var.getName()}，发生错误！")
                return

        # mapfoldwi第1个输出是index
        _Lindex = builder.create_local("_L011", "int32")
        Equation.getLefts().add(_Lindex)

        # mapfoldwi第2个输出是enable
        _Lenable = builder.create_local("_L022", "bool")
        Equation.getLefts().add(_Lenable)

        # mapfoldwi第3个之后的输出才是有意义的
        for index, output in enumerate(expr['outputs']):
            var_kind, var = self.determine_var_kind(output)
            # 参与acc迭代的输出类型不变
            if index < int(accumulators):
                if var_kind == "Output":
                    print(f"⚠️ 对输出{output}计算后赋值，发生错误！")
                    # TODO 例如：Output_01 = / (_L2, _L3)的情况处理
                    # _L2 = self.create_local_E(outType, out)
                    # self.create_output_equation("_L2", output)
                    return

                elif var_kind == "Local":
                    print(f"⚠️ 局部变量{output}被再次写入，发生错误！")
                    return

                else:
                    print(f"🟡 未找到变量{output}, 开始创建")
                    outType = self.get_output_port_data_type(calledOp, index)
                    _L2 = self.create_local_E(outType, output)
                    Equation.getLefts().add(_L2)

            # 不参与acc的为数组，需要升高维度，用table
            else:
                if var_kind == "Output":
                    print(f"⚠️ 对输出{output}计算后赋值，发生错误！")
                    # TODO 例如：Output_01 = / (_L2, _L3)的情况处理
                    # _L2 = self.create_local_E(outType, out)
                    # self.create_output_equation("_L2", output)
                    return

                elif var_kind == "Local":
                    print(f"⚠️ 局部变量{output}被再次写入，发生错误！")
                    return

                else:
                    print(f"🟡 未找到变量{output}, 开始创建")
                    outType = self.get_output_port_data_type(calledOp, index)
                    baseType = outType.getType().getName()
                    type_name = baseType + "^" + size
                    type_obj = self.create_type_from_string(type_name)
                    _L2 = self.create_local_E(type_obj, output)
                    Equation.getLefts().add(_L2)

        for index, output in enumerate(expr['outputs']):
            # GE2
            if index == 0:
                GE2 = self.create_EquationGE(Equation, output, 5000, 1000, 2000, 3000)
            else:
                self.lx_to_ge[self.current_full_dir][output] = GE2

        Equation.setRight(callExpression)
        self.current_canvas.getData().add(Equation)
        self.EditorPragmasUtil.setOid(Equation, self.generate_oid())

        # if条件的连线
        GE1 = self.lx_to_ge[self.current_full_dir][cond]
        self.create_Edge(GE1, GE2, 1, 1)

        # 输入的连线
        for index, input in enumerate(expr['inputs']):
            GE1 = self.lx_to_ge[self.current_full_dir][input]
            self.create_Edge(GE1, GE2, 1, index + 2)


    def get_output_port_data_type(self, operator, index: int):
        """
        根据 Operator 对象和输出端口下标，获取输出端口的类型
        - operator: Operator 对象（Scade API）
        - index: 输出端口在 getOutputs() 中的索引

        返回:
        - 数据类型对象（NamedType、ArrayType 等），如果存在
        - None，如果下标超出范围或 operator 为 None
        """
        outputs = operator.getOutputs()
        if index < 0 or index >= len(outputs):
            print(f"⚠️ 输出端口下标 {index} 超出范围 (0 ~ {len(outputs) - 1})")
            return None

        port = outputs[JInt(index)]  # 这里强制用 Java int
        data_type = port.getType()
        print(f"✅ 输出端口 index={index} 的数据类型: {data_type}")
        return data_type


    def create_operator_diagram(self, diagramName: str):
        self.Operator_Pragma = self.theEditorPragmasFactory.createOperator()
        self.Operator_Pragma.setNodeKind("graphical")
        self.Operator_Diagram = self.theEditorPragmasFactory.createNetDiagram()
        self.Operator_Diagram.setName(diagramName)
        self.Operator_Diagram.setFormat("A4 (210 297)")
        self.Operator_Diagram.setLandscape(True)
        self.Operator_Diagram.setOid(self.generate_oid())
        self.Operator_Pragma.getDiagrams().add(self.Operator_Diagram)
        self.current_canvas.getPragmas().add(self.Operator_Pragma)


    def create_state_machine_with_transitions(self, sm_name: str, states: list[str],
                                              transitions: list[tuple[str, str, str]]):
        """
        创建一个状态机，添加状态和 transitions。
        - sm_name: 状态机名称
        - states: 状态名称列表，例如 ["S1", "S2", "S3"]
        - transitions: 迁移列表，每个元素是 (source_name, target_name, condition_expr)
        """
        if self.current_operator is None:
            print("❌ 当前未选择 Operator")
            return None

        # 创建状态机
        sm = self.theScadeFactory.createStateMachine()
        sm.setName(sm_name)
        sm_oid = self.generate_oid(f"SM{sm_name}Oid")
        self.EditorPragmasUtil.setOid(sm, sm_oid)
        self.current_canvas.getData().add(sm)
        self.create_StateMachineGE(sm, "sm_name")
        print(f"✅ 创建状态机: {sm_name}")

        # 创建状态
        state_objs = {}
        x = 2000
        y = 3000
        for idx, state_name in enumerate(states):
            state = self.theScadeFactory.createState()
            state.setName(state_name)
            state_oid = self.generate_oid(f"SM{sm_name}{state_name}Oid")
            self.EditorPragmasUtil.setOid(state, state_oid)
            self.create_StateGE(state, state_name, x, y)
            # 第一个状态设为初始态
            if idx == 0:
                state.setInitial(True)
                print(f"🟢 设置初始状态: {state_name}")

            sm.getStates().add(state)
            state_objs[state_name] = state
            print(f"✅ 创建状态: {state_name}")
            x = x + 3000
            y = y + 2000

        # 创建 transitions
        for source_name, target_name, condition_expr in transitions:
            source_state = state_objs.get(source_name)
            target_state = state_objs.get(target_name)

            if source_state is None or target_state is None:
                print(f"⚠️ Transition 跳过：找不到 {source_name} 或 {target_name}")
                continue

            transition = self.theScadeFactory.createTransition()
            transition.setTarget(target_state)
            transition_oid = self.generate_oid(f"SM{sm_name}{source_name}{target_name}T")
            self.EditorPragmasUtil.setOid(transition, transition_oid)

            # 设置条件表达式（如果给了）
            if condition_expr:
                var_kind_i, var_i = self.determine_var_kind("_L1")
                rightExpr = self.theScadeFactory.createIdExpression()
                rightExpr.setPath(var_i)
                transition.setCondition(rightExpr)
                print(f"🔵 为 {source_name}->{target_name} 设置条件: {condition_expr}")

            # 将 transition 添加到 source_state 的 unless 中
            source_state.getUnless().add(transition)
            self.create_TransitionGE(transition, condition_expr)
            print(f"✅ 创建 Transition: {source_name} -> {target_name}")

        print("✅ 状态机及所有 Transition 创建完成")
        return sm


    def parse_expression_line(self, line):
        line = line.strip()
        # 1. 先匹配带括号的复杂运算
        complex_match = re.match(r"([\w,\s]+)=\s*([^\s(]+)\s*\((.*)\)", line)
        if complex_match:
            outputs = [o.strip() for o in complex_match.group(1).split(',')]
            operator = complex_match.group(2)
            inputs = [i.strip() for i in complex_match.group(3).split(',')]
            return {"outputs": outputs, "operator": operator, "inputs": inputs}

        # 2. 匹配简单赋值（无括号）
        simple_match = re.match(r"([\w,\s]+)=\s*(\S+)", line)
        if simple_match:
            outputs = [o.strip() for o in simple_match.group(1).split(',')]
            #operator = "assign"   # 直接赋值操作
            inputs = [simple_match.group(2)]
            return {"outputs": outputs[0], "inputs": inputs[0]}
        return None

    def parse_mapfoldwi_expression(self, expr_line: str) -> dict:
        """
        解析形如:
        _L4, _L5, _L6, _L7 = (mapfoldwi 2 Operator2 <<5>> if _L1)(_L2, _L3)
        返回一个 dict:
        {
            'outputs': ['_L4', '_L5', '_L6', '_L7'],
            'operator': 'mapfoldwi',
            'suboperator': 'Operator2',
            'accumulators': '2',
            'size': '5',
            'condition': '_L1',
            'inputs': ['_L2', '_L3']
        }
        """
        # 提取 = 左侧
        left_right = expr_line.split('=')
        if len(left_right) != 2:
            raise ValueError(f"无效的 mapfoldwi 表达式: {expr_line}")

        left_part = left_right[0].strip()
        right_part = left_right[1].strip()
        outputs = [o.strip() for o in left_part.split(',')]

        # operator 部分: (mapfoldwi 2 Operator2 <<5>> if _L1)
        op_pattern = r"\((mapfoldwi)\s+(\d+)\s+([a-zA-Z0-9_]+)\s+<<\s*(\d+)\s*>>\s+if\s+([a-zA-Z0-9_]+)\)"
        op_match = re.search(op_pattern, right_part)
        if not op_match:
            raise ValueError(f"无法解析 operator 部分: {expr_line}")

        operator = op_match.group(1)
        accumulators = op_match.group(2)
        suboperator = op_match.group(3)
        size = op_match.group(4)
        condition = op_match.group(5)

        # inputs 部分: (...) 在 operator 部分之后
        input_pattern = r"\)\s*\((.*?)\)"
        input_match = re.search(input_pattern, right_part)
        if not input_match:
            raise ValueError(f"无法解析 inputs 部分: {expr_line}")

        inputs_str = input_match.group(1)
        inputs = [i.strip() for i in inputs_str.split(',')]

        return {
            'outputs': outputs,
            'operator': operator,
            'subOperator': suboperator,
            'accumulators': accumulators,
            'size': size,
            'condition': condition,
            'inputs': inputs
        }


    def parse_text_block1(self, text):
        expressions = []
        for line in text.strip().splitlines():
            parsed = self.parse_expression_line(line)
            if parsed:
                expressions.append(parsed)

        for expr in expressions:
            # 有操作符的情况
            if 'operator' in expr and expr['operator']:
                #self.create_buildInOperator_equation(expr)
                self.create_operator_equation(expr)
            else:
                # 赋值类
                left = expr.get('outputs')
                right = expr.get('inputs')
                # 判断右侧是否为输入变量
                right_kind, _ = self.determine_var_kind(right)
                # 判断左侧是否为输出变量
                left_kind, _ = self.determine_var_kind(left)

                if right_kind == "Input":
                    self.create_input_equation(right, left)
                elif left_kind == "Output":
                    self.create_output_equation(right, left)
                else:
                    print(f"⚠️ 无法识别赋值类型: {right} = {left}")


    def parse_text_block(self, text):
        expressions = []
        for line in text.strip().splitlines():
            # 判断是否是 mapfoldwi 语句
            if "mapfoldwi" in line:
                parsed = self.parse_mapfoldwi_expression(line)
            else:
                parsed = self.parse_expression_line(line)

            if parsed:
                expressions.append(parsed)

        self.expressions = expressions  # 保存到对象属性

        for expr in expressions:
            # mapfoldwi 需要特殊处理
            if expr.get('operator') == "mapfoldwi":
                self.create_mapfoldwi_equation(expr)  # 你自己实现它
                continue

            # 其他操作符的情况
            if 'operator' in expr and expr['operator']:
                # self.create_buildInOperator_equation(expr)
                self.create_operator_equation(expr)
            else:
                # 赋值类
                left = expr.get('outputs')
                right = expr.get('inputs')
                # 判断右侧是否为输入变量
                right_kind, _ = self.determine_var_kind(right)
                # 判断左侧是否为输出变量
                left_kind, _ = self.determine_var_kind(left)

                if right_kind == "Input":
                    self.create_input_equation(right, left)
                elif left_kind == "Output":
                    self.create_output_equation(right, left)
                else:
                    print(f"⚠️ 无法识别赋值类型: {right} = {left}")



if __name__ == "__main__":
    # 示例文本
    input_text = """
    _L1 = Input_01
    _L2 = Input_02
    _L3 = Input_03
    _L4, _L5 = (mapfoldwi 1 Operator2 <<5>> if _L1)(_L2, _L3)
    Output_01 = _L4
    Output_02 = _L5
    """

    builder = SCADE_Builder()
    builder.start_jvm()
    builder.init_scade_classes()

    #project_dir = r"C:\example1"  # 这里可以自定义
    #project_name = "example1"  # 这里可以自定义
    #package_name = "Package1"  # 这里可以自定义
    #operator_name = "Operator1"  # 这里可以自定义
    #builder.init_project_and_model("C:\\example1", "example1")
    builder.load_project_and_model("C:\\example2", "example2")
    builder.switch_to_operator_by_path("Package1::Operator1/")

    #builder.switch_to_operator_by_path("Package1::Package2::Operator3/SM1:State1:SM2:State2:SM3:State3:")

    #builder.create_package("Package1")
    builder.create_operator("Operator3")
    builder.create_operator_diagram("operator3_diagram")

    builder.create_input("Input_01", "bool")
    builder.create_input("Input_02", "bool")
    builder.create_input("Input_03", "bool^5")

    builder.create_output("Output_01", "bool")
    builder.create_output("Output_02", "bool^5")

    # builder.create_local("uint32", "Input222")

    builder.parse_text_block(input_text)

    # 假设当前已经切换到目标 Operator
    #builder.create_operator_diagram("SM1_diagram")
    #builder.create_state_machine_with_transitions(
    #    sm_name="SM1",
    #    states=["S1", "S2", "S3", "S4"],
    #    transitions=[
    #        ("S1", "S2", "_L1"),
    #        ("S2", "S3", "_L2"),
    #        ("S2", "S4", "_L3"),
    #        ("S3", "S4", "_L4"),
    #    ]
    #)

    builder.save_project()
    builder.shutdown_jvm()
