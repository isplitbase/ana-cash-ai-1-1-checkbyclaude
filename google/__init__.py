# stub package
# 実体の google.cloud(storage 等) を import できるよう名前空間を拡張する。
# (PROJECT_ROOT が PYTHONPATH に入るため、この stub が site-packages の google を
#  隠してしまうのを防ぐ)
from pkgutil import extend_path
__path__ = extend_path(__path__, __name__)
