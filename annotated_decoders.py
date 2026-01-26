"""
【设计模式标注】解码器模块 - 装饰器模式应用
============================================

本模块实现了 Base64Decoder 和 QuotedPrintableDecoder 两个解码器类。

【装饰器模式应用】
这两个类体现了装饰器模式的核心思想：
1. 组件（Component）：SupportsWrite 协议定义了 write、close、finalize 接口
2. 具体组件：BytesIO、文件对象等实现了 SupportsWrite 接口的实际对象
3. 装饰器：Base64Decoder 和 QuotedPrintableDecoder 包装具体组件
4. 透明性：装饰器与被装饰对象实现相同的接口，可互换使用

【数据流处理模式】
两个解码器都采用"流式处理 + 缓存管理"的模式：
- 输入：任意大小的字节数据块
- 处理：对输入数据进行格式解码
- 输出：将解码后的数据写入底层对象
- 缓存：处理跨块边界的不完整编码单元
"""

from __future__ import annotations

import base64
import binascii
from typing import TYPE_CHECKING

from .exceptions import DecodeError

# 【类型标注】TYPE_CHECKING 块用于类型检查时导入，避免运行时循环依赖
if TYPE_CHECKING:  # pragma: no cover
    from typing import Protocol, TypeVar

    # 【类型系统】协变类型变量，用于支持逆变参数的协议定义
    _T_contra = TypeVar("_T_contra", contravariant=True)

    class SupportsWrite(Protocol[_T_contra]):
        """
        【接口定义】支持写入操作的协议
        
        【协议模式】
        Python 的 Protocol 实现了结构化子类型（duck typing），
        任何具有 write 方法的对象都被视为 SupportsWrite 的子类型。
        
        【方法签名】
        write 方法接收字节数据，返回写入的字节数（object 类型是为了兼容各种返回值）
        close 和 finalize 是可选方法（通过注释说明）
        """

        def write(self, __b: _T_contra) -> object: ...

        # No way to specify optional methods. See
        # https://github.com/python/typing/issues/601
        # close() [Optional]
        # finalize() [Optional]


# =============================================================================
# Base64Decoder 类实现
# =============================================================================

class Base64Decoder:
    """
    【设计模式】装饰器模式 - 具体装饰器
    
    【功能说明】
    提供流式 Base64 数据解码能力，将输入的 Base64 编码数据解码为原始字节。
    
    【装饰器模式结构】
    - 目标对象：任何实现了 SupportsWrite 协议的对象（如文件、BytesIO）
    - 装饰器：Base64Decoder，在写入操作前后添加 Base64 解码逻辑
    - 透明性：调用方无需关心底层对象是否被包装
    
    【使用示例】
    ```python
    from python_multipart.decoders import Base64Decoder
    fd = open("output.txt", "wb")
    decoder = Base64Decoder(fd)
    decoder.write("Zm9vYmFy")  # "foobar" in Base64
    decoder.finalize()
    decoder.close()
    ```
    
    【缓存机制】
    Base64 编码要求输入长度为 4 的倍数（每 4 个字符解码为 3 个字节）。
    当写入数据长度不是 4 的倍数时，剩余的字节被缓存到下一次写入。
    这种设计支持任意大小的数据块写入，无需预先知道总长度。
    
    【生命周期】
    1. 实例化：创建解码器，初始化缓存
    2. 写入阶段：多次调用 write 方法，每次解码并转发数据
    3. 结束阶段：调用 finalize 确保所有缓存数据被处理
    4. 清理阶段：调用 close 关闭底层对象
    """

    def __init__(self, underlying: "SupportsWrite[bytes]") -> None:
        """
        【构造函数】初始化 Base64 解码器
        
        【参数】
        underlying：底层写入目标，任何支持 write(data: bytes) -> int 的对象
        
        【初始化内容】
        - self.cache：字节数组，存储未完成的 Base64 编码单元
        - self.underlying：底层对象的引用，用于转发解码后的数据
        """
        self.cache = bytearray()
        self.underlying = underlying

    def write(self, data: bytes) -> int:
        """
        【算法实现】流式 Base64 解码算法
        
        【算法步骤】
        1. 预处理：将缓存的未完成数据与新输入拼接
        2. 截取：按照 4 的倍数截取完整的编码单元
        3. 解码：使用 base64.b64decode 进行解码
        4. 写入：将解码数据写入底层对象
        5. 缓存：保存剩余的不完整编码单元
        
        【错误处理】
        - binascii.Error：Base64 格式错误时抛出 DecodeError
        - finalize 时检查缓存中是否还有未处理数据
        
        【返回值】
        返回输入数据的总长度（包含缓存部分），用于流式处理的进度追踪
        """
        # 【边界检查】如果有缓存数据，需要与新数据拼接
        if len(self.cache) > 0:
            data = bytes(self.cache) + data

        # 【算法核心】Base64 要求每 4 个字符解码为 3 个字节
        # 计算可以完整解码的数据长度（向下取整为 4 的倍数）
        decode_len = (len(data) // 4) * 4
        val = data[:decode_len]

        # 解码并写入底层对象
        if len(val) > 0:
            try:
                decoded = base64.b64decode(val)
            except binascii.Error:
                raise DecodeError("There was an error raised while decoding base64-encoded data.")

            self.underlying.write(decoded)

        # 处理剩余数据：如果长度不是 4 的倍数，缓存不完整部分
        remaining_len = len(data) % 4
        if remaining_len > 0:
            self.cache[:] = data[-remaining_len:]
        else:
            self.cache[:] = b""

        return len(data)

    def close(self) -> None:
        """
        【资源管理】关闭解码器
        
        【实现模式】
        代理模式：如果底层对象有 close 方法，则调用该方法
        这种设计确保了资源释放的透明性
        """
        if hasattr(self.underlying, "close"):
            self.underlying.close()

    def finalize(self) -> None:
        """
        【生命周期】结束解码过程
        
        【语义】
        finalize 表示"所有数据已写入，不再有新数据"
        此时应该确保缓存中的数据都被正确处理
        
        【错误情况】
        如果 finalize 时缓存中仍有数据，说明 Base64 编码不完整
        这可能是数据传输错误或编码错误
        
        【责任链】
        如果底层对象有 finalize 方法，也需要调用它
        例如：Base64Decoder(File(...)) 链式调用
        """
        if len(self.cache) > 0:
            raise DecodeError(
                "There are %d bytes remaining in the Base64Decoder cache when finalize() is called" % len(self.cache)
            )

        if hasattr(self.underlying, "finalize"):
            self.underlying.finalize()

    def __repr__(self) -> str:
        """
        【调试支持】对象字符串表示
        
        【格式】
        Base64Decoder(underlying=<底层对象repr>)
        """
        return f"{self.__class__.__name__}(underlying={self.underlying!r})"


# =============================================================================
# QuotedPrintableDecoder 类实现
# =============================================================================

class QuotedPrintableDecoder:
    """
    【设计模式】装饰器模式 - 具体装饰器
    
    【功能说明】
    提供流式 Quoted-Printable 数据解码能力。
    Quoted-Printable 是一种邮件传输编码，使用 =XX 表示特殊字符。
    
    【编码规则】
    - 可打印 ASCII 字符（33-60, 62-126）直接表示
    - 空格和制表符使用 _ 或 =20 表示
    - 软换行（末尾 =）表示下一行继续
    - 其他字符使用 =XX 表示，XX 是字符的十六进制 ASCII 码
    
    【与 Base64Decoder 的比较】
    - 共同点：都实现装饰器接口，都使用缓存处理跨块数据
    - 不同点：Quoted-Printable 没有严格的块大小要求
             但软换行（= 后跟 CRLF）需要特殊处理
    """

    def __init__(self, underlying: "SupportsWrite[bytes]") -> None:
        """
        【构造函数】初始化 Quoted-Printable 解码器
        
        【初始化内容】
        - self.cache：字节字符串，存储跨块的不完整编码
        - self.underlying：底层对象的引用
        """
        self.cache = b""
        self.underlying = underlying

    def write(self, data: bytes) -> int:
        """
        【算法实现】流式 Quoted-Printable 解码算法
        
        【算法核心】
        Quoted-Printable 的关键是识别软换行（Soft Line Break）：
        当数据末尾出现 = 符号时，表示下一行的数据继续当前编码
        
        【算法步骤】
        1. 预处理：拼接缓存数据
        2. 检测软换行：检查最后两个字节是否包含 =
        3. 拆分：将有完整编码的部分和待缓存的部分分离
        4. 解码：使用 binascii.a2b_qp 解码
        5. 缓存：保存不完整的部分供下次处理
        
        【特殊处理】
        = 后跟 CRLF（\r\n）表示软换行，实际内容跨行连续
        这种情况下 =XX 不需要解码，直接忽略软换行标记
        """
        # 预处理：拼接缓存
        if len(self.cache) > 0:
            data = self.cache + data

        # 检测软换行：如果末尾有 =，可能是不完整的编码或软换行标记
        if data[-2:].find(b"=") != -1:
            enc, rest = data[:-2], data[-2:]
        else:
            enc = data
            rest = b""

        if len(enc) > 0:
            self.underlying.write(binascii.a2b_qp(enc))

        self.cache = rest
        return len(data)

    def close(self) -> None:
        """
        【资源管理】关闭解码器
        
        【实现】代理到底层对象的 close 方法
        """
        if hasattr(self.underlying, "close"):
            self.underlying.close()

    def finalize(self) -> None:
        """
        【生命周期】结束解码过程
        
        【特殊处理】
        与 Base64Decoder 不同，QuotedPrintableDecoder 在 finalize 时
        会尝试解码缓存中的剩余数据（如果有的话）。
        这是因为 Quoted-Printable 的软换行可能在任意位置出现，
        finalize 时的缓存可能只是正常的编码数据。
        """
        if len(self.cache) > 0:  # pragma: no cover
            self.underlying.write(binascii.a2b_qp(self.cache))
            self.cache = b""

        if hasattr(self.underlying, "finalize"):
            self.underlying.finalize()

    def __repr__(self) -> str:
        """
        【调试支持】对象字符串表示
        """
        return f"{self.__class__.__name__}(underlying={self.underlying!r})"
