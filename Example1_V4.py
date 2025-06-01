from logging import getLevelName

import jpype
import uuid, os, re

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

        self.Operator1_Pragma = None
        self.Operator1_Diagram = None

        # 当前工作目录指针
        self.current_package = None
        self.current_operator = None
        self.current_full_dir = "Package1::Operator1/"

        # _Lx临时变量相关
        self.lx_to_ge = {}
        self.lx_to_ge[self.current_full_dir] = {}

        self.Equation1 = None
        self.Equation2 = None
        self.Equation3 = None

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
        self.baseURI = self.URI.createFileURI(project_dir)
        self.projectURI = self.baseURI.appendSegment(f"{project_name}.etp")
        self.resourceSet = self.ResourceSetImpl()
        self.project = self.ScadeModelReader.getProject(self.projectURI, self.resourceSet)
        self.mainModel = self.ScadeModelReader.loadModel(self.projectURI, self.resourceSet)
        print("✅ 项目和模型初始化完成")

    def find_package(self, pkg_name: str):
        all_contents = self.EcoreUtil.getAllContents(self.mainModel, True)
        while all_contents.hasNext():
            obj = all_contents.next()
            if obj.eClass().getName() == "Package":
                if obj.getName() == pkg_name:
                    self.current_package = obj
                    print(f"✅ 切换到 Package: {pkg_name}")
                    return obj
        print(f"❌ 未找到 Package: {pkg_name}")
        return None

    def find_operator(self, pkg, op_name: str):
        if pkg is None:
            print("❌ 当前未选中 Package")
            return None
        declarations = pkg.getDeclarations()
        for decl in declarations:
            if decl.eClass().getName() == "Operator":
                if decl.getName() == op_name:
                    self.current_operator = decl
                    print(f"✅ 切换到 Operator: {op_name}")
                    return decl
        print(f"❌ 未找到 Operator: {op_name}")
        return None

    def switch_to_operator_by_path(self, path_str: str):
        """
        根据路径如：
            - "Defs::Package1::Package2::CruiseControl/" （嵌套结构）
            - "Operator3/" （根级 operator）
        自动切换当前的 package 和 operator。
        """
        self.current_full_dir = path_str
        segments = [seg for seg in path_str.strip("/").split("::") if seg]
        if not segments:
            print("❌ 空路径")
            return None

        # 只有一个路径段，视为顶层 operator
        if len(segments) == 1:
            operator_name = segments[0]
            if hasattr(self.mainModel, "getOperators"):
                for op in self.mainModel.getOperators():
                    print(op.getName())
                    if op.getName() == operator_name:
                        self.current_operator = op
                        print(f"✅ 成功切换到顶层 Operator: {self.current_operator}")
                        return op
            print(f"❌ 未找到顶层 Operator: {operator_name}")
            return None

        # 多层路径：第一段是根包
        root_pkg_name = segments[0]
        current = None
        for obj in self.mainModel.getDeclarations():
            if hasattr(obj, "getName") and obj.eClass().getName() == "Package" and obj.getName() == root_pkg_name:
                print(obj.getName())
                current = obj
                break
        if current is None:
            print(f"❌ 未找到根 Package: {root_pkg_name}")
            return None

        # 中间段：逐层 getPackages() 查找子包
        for pkg_name in segments[1:-1]:
            next_pkg = None
            for pkg in current.getDeclarations():
                if pkg.getName() == pkg_name:
                    print(pkg.getName())
                    next_pkg = pkg
                    break
            if next_pkg is None:
                print(f"❌ 未找到子包: {pkg_name}")
                return None
            current = next_pkg

        # 最后一级是 Operator
        operator_name = segments[-1]
        for op in current.getOperators():
            if op.getName() == operator_name:
                print(op.getName())
                self.current_package = current
                self.current_operator = op
                print(f"✅ 成功切换到 Package: {self.current_package}")
                print(f"✅ 成功切换到 Operator: {self.current_operator}")
                return op

        print(f"❌ 未找到 Operator: {operator_name}")
        return None


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

    def create_operator(self, operator_name: str):
        Operator = self.theScadeFactory.createOperator()
        Operator.setName(operator_name)
        Operator.setKind(self.OperatorKind.FUNCTION_LITERAL)
        self.current_package.getDeclarations().add(Operator)
        # codegen pragma
        Operator_KCGPragma = self.theCodegenPragmasFactory.createPragma()
        Operator_KCGPragma.setData(f"C:name {operator_name}")
        Operator.getPragmas().add(Operator_KCGPragma)
        print(f"✅ Operator {operator_name} 创建完成")
        self.current_operator = Operator
        return Operator

    def create_input(self, type: str, input_name="Input1"):
        if self.current_operator is None:
            print("❌ 当前未选择 Operator")
            return None

        # 名称重复检查
        for existing_input in self.current_operator.getInputs():
            if existing_input.getName() == input_name:
                print(f"⚠️ 输入名 '{input_name}' 已存在于 Operator '{self.current_operator.getName()}' 中，拒绝添加。")
                return existing_input
        type = self.find_typeObject(type)
        Input = self.theScadeFactory.createVariable()
        Input.setName(input_name)
        Input_Type = self.theScadeFactory.createNamedType()
        Input_Type.setType(type)
        Input.setType(Input_Type)
        self.current_operator.getInputs().add(Input)
        return Input

    def create_output(self, type: str, output_name="Output1"):
        if self.current_operator is None:
            print("❌ 当前未选择 Operator")
            return None

        # 名称重复检查
        for existing_output in self.current_operator.getOutputs():
            if existing_output.getName() == output_name:
                print(f"⚠️ 输入名 '{output_name}' 已存在于 Operator '{self.current_operator.getName()}' 中，拒绝添加。")
                return existing_output
        type = self.find_typeObject(type)
        Output = self.theScadeFactory.createVariable()
        Output.setName(output_name)
        Output_Type = self.theScadeFactory.createNamedType()
        Output_Type.setType(type)
        Output.setType(Output_Type)
        self.current_operator.getOutputs().add(Output)
        return Output

    # 根据字符串创建
    def create_local(self, type: str, local_name="Local1"):
        if self.current_operator is None:
            print("❌ 当前未选择 Operator")
            return None

        # 名称重复检查
        for existing_local in self.current_operator.getLocals():
            if existing_local.getName() == local_name:
                print(f"⚠️ 输入名 '{local_name}' 已存在于 Operator '{self.current_operator.getName()}' 中，拒绝添加。")
                return existing_local
        type = self.find_typeObject(type)
        Local = self.theScadeFactory.createVariable()
        Local.setName(local_name)
        Local_Type = self.theScadeFactory.createNamedType()
        Local_Type.setType(type)
        Local.setType(Local_Type)
        self.current_operator.getLocals().add(Local)
        return Local

    # 根据类型创建，这里的type不是string
    def create_local_E(self, type, local_name="Local1"):
        if self.current_operator is None:
            print("❌ 当前未选择 Operator")
            return None

        # 名称重复检查
        for existing_local in self.current_operator.getLocals():
            if existing_local.getName() == local_name:
                print(f"⚠️ 输入名 '{local_name}' 已存在于 Operator '{self.current_operator.getName()}' 中，拒绝添加。")
                return existing_local

        # 关键：克隆 type_obj，避免“引用转移”
        new_named_type = self.theScadeFactory.createNamedType()
        new_named_type.setType(type.getType())  # 复制 Type 引用，而不是直接共享整个 NamedType

        Local = self.theScadeFactory.createVariable()
        Local.setName(local_name)
        Local.setType(new_named_type)
        self.current_operator.getLocals().add(Local)
        return Local

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
        self.current_operator.getData().add(Equation)
        self.EditorPragmasUtil.setOid(Equation, self.generate_oid())
        return Equation


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

            self.Equation1 = self.create_input_equation_E(var_i, _L1)

            # GE1
            GE1 = self.theEditorPragmasFactory.createEquationGE()
            GE1.setEquation(self.Equation1)
            pos1 = self.theEditorPragmasFactory.createPoint()
            pos1.setX(1000)
            pos1.setY(1000)
            GE1.setPosition(pos1)
            size1 = self.theEditorPragmasFactory.createSize()
            size1.setWidth(1000)
            size1.setHeight(1000)
            GE1.setSize(size1)
            self.Operator1_Diagram.getPresentationElements().add(GE1)
            self.lx_to_ge[self.current_full_dir][output] = GE1

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
            self.Equation3 = self.theScadeFactory.createEquation()
            self.Equation3.getLefts().add(var)
            rightExpr = self.theScadeFactory.createIdExpression()
            rightExpr.setPath(_L2)
            self.Equation3.setRight(rightExpr)
            self.current_operator.getData().add(self.Equation3)
            self.EditorPragmasUtil.setOid(self.Equation3, self.generate_oid())

            # GE3
            GE3 = self.theEditorPragmasFactory.createEquationGE()
            GE3.setEquation(self.Equation3)
            pos3 = self.theEditorPragmasFactory.createPoint()
            pos3.setX(10000)
            pos3.setY(1000)
            GE3.setPosition(pos3)
            size3 = self.theEditorPragmasFactory.createSize()
            size3.setWidth(1000)
            size3.setHeight(1000)
            GE3.setSize(size3)
            self.Operator1_Diagram.getPresentationElements().add(GE3)
            self.lx_to_ge[self.current_full_dir][output] = GE3

            GE2 = self.lx_to_ge[self.current_full_dir][input]

            # Edge2
            Edge2 = self.theEditorPragmasFactory.createEdge()
            Edge2.setSrcEquation(GE2)
            Edge2.setDstEquation(GE3)
            Edge2.setLeftVarIndex(1)
            Edge2.setRightExprIndex(1)
            pt1 = self.theEditorPragmasFactory.createPoint()
            pt1.setX(1000)
            pt1.setY(1000)
            pt4 = self.theEditorPragmasFactory.createPoint()
            pt4.setX(1000)
            pt4.setY(1000)
            Edge2.getPositions().add(pt1)
            Edge2.getPositions().add(pt4)
            self.Operator1_Diagram.getPresentationElements().add(Edge2)

        # Output1未定义
        else:
            print(f"⚠️ 未找到输出{var.getName()}")


    def create_buildInOperator_equation(self, expr):
        print(f"Operator: {expr['operator']}")
        naryOp = self.theScadeFactory.createNAryOp()
        naryOp.setOperator(expr['operator'])
        outType = None
        _L1 = None
        _L2 = None
        GE2 = None

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
                naryOp.getOperands().add(rightExpr)

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

                self.Equation2 = self.theScadeFactory.createEquation()
                self.Equation2.getLefts().add(_L2)
                self.Equation2.setRight(naryOp)
                self.current_operator.getData().add(self.Equation2)
                self.EditorPragmasUtil.setOid(self.Equation2, self.generate_oid())

                # GE2
                GE2 = self.theEditorPragmasFactory.createEquationGE()
                GE2.setEquation(self.Equation2)
                pos2 = self.theEditorPragmasFactory.createPoint()
                pos2.setX(5000)
                pos2.setY(1000)
                GE2.setPosition(pos2)
                size2 = self.theEditorPragmasFactory.createSize()
                size2.setWidth(1000)
                size2.setHeight(1000)
                GE2.setSize(size2)
                self.Operator1_Diagram.getPresentationElements().add(GE2)
                self.lx_to_ge[self.current_full_dir][output] = GE2

        idx = 1
        for input in expr['inputs']:
            # Edge1
            GE1 = self.lx_to_ge[self.current_full_dir][input]

            Edge1 = self.theEditorPragmasFactory.createEdge()
            Edge1.setSrcEquation(GE1)
            Edge1.setDstEquation(GE2)
            Edge1.setLeftVarIndex(1)
            Edge1.setRightExprIndex(idx)
            pt1 = self.theEditorPragmasFactory.createPoint()
            pt1.setX(1000)
            pt1.setY(1000)
            pt4 = self.theEditorPragmasFactory.createPoint()
            pt4.setX(1000)
            pt4.setY(1000)
            Edge1.getPositions().add(pt1)
            Edge1.getPositions().add(pt4)
            self.Operator1_Diagram.getPresentationElements().add(Edge1)
            idx = idx + 1

    def create_operator_diagram(self):
        self.Operator1_Pragma = self.theEditorPragmasFactory.createOperator()
        self.current_operator.getPragmas().add(self.Operator1_Pragma)
        self.Operator1_Pragma.setNodeKind("graphical")
        self.Operator1_Diagram = self.theEditorPragmasFactory.createNetDiagram()
        self.Operator1_Diagram.setName("Operator1_diagram")
        self.Operator1_Diagram.setFormat("A4 (210 297)")
        self.Operator1_Diagram.setLandscape(True)
        self.Operator1_Diagram.setOid("Op1DiagOid")
        self.Operator1_Pragma.getDiagrams().add(self.Operator1_Diagram)
        print("✅ Operator1 Diagram、GE、Edge 创建完成")



def mainaa():
    builder = SCADE_Builder()
    builder.start_jvm()
    builder.init_scade_classes()
    project_dir = r"C:\example1"         # 这里可以自定义
    project_name = "example1"            # 这里可以自定义
    package_name = "Package1"            # 这里可以自定义
    operator_name = "Operator1"          # 这里可以自定义
    builder.init_project_and_model(project_dir, project_name)
    #builder.load_project_and_model(project_dir, project_name)
    #builder.switch_to_operator_by_path("Package1::Package2::Package3::Operator7/")

    #builder.create_local("uint32", "Input222")
    builder.create_package(package_name)
    builder.create_operator(operator_name)

    builder.create_input("uint32", "Input222")
    #builder.create_output("uint32", "Otnput222")

    Equation1, Equation2, Equation3 = builder.create_operator_io_and_equations()
    builder.create_operator_diagram(Equation1, Equation2, Equation3)
    builder.save_project()
    builder.shutdown_jvm()

def parse_expression_line(line):
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
        operator = "assign"   # 直接赋值操作
        inputs = [simple_match.group(2)]
        return {"outputs": outputs, "operator": operator, "inputs": inputs}
    return None

def parse_text_block(text):
    expressions = []
    for line in text.strip().splitlines():
        parsed = parse_expression_line(line)
        if parsed:
            expressions.append(parsed)
    return expressions


if __name__ == "__main__":
    # 示例文本
    input_text = """
    _L4 = + (_L1, _L2, _L3)
    _L5 = * (_L3, _L4)
    """

    builder = SCADE_Builder()
    builder.start_jvm()
    builder.init_scade_classes()
    project_dir = r"C:\example1"  # 这里可以自定义
    project_name = "example1"  # 这里可以自定义
    package_name = "Package1"  # 这里可以自定义
    operator_name = "Operator1"  # 这里可以自定义
    builder.init_project_and_model(project_dir, project_name)
    # builder.load_project_and_model(project_dir, project_name)
    # builder.switch_to_operator_by_path("Package1::Package2::Package3::Operator7/")

    # builder.create_local("uint32", "Input222")
    builder.create_package(package_name)
    builder.create_operator(operator_name)

    builder.create_input("uint32", "Input_01")
    builder.create_input("uint32", "Input_02")
    builder.create_input("uint32", "Input_03")
    builder.create_output("uint32", "Output_01")
    builder.create_output("uint32", "Output_02")

    expressions = parse_text_block(input_text)

    builder.create_operator_diagram()

    # 返回所有表达式
    print("所有表达式提取结果：")
    builder.create_input_equation("Input_01", "_L1")
    builder.create_input_equation("Input_02", "_L2")
    builder.create_input_equation("Input_03", "_L3")
    for expr in expressions:
        builder.create_buildInOperator_equation(expr)
        #break
    builder.create_output_equation("_L4", "Output_01")
    builder.create_output_equation("_L5", "Output_02")

    builder.save_project()
    builder.shutdown_jvm()