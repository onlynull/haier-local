"""实体映射、中文名称、图标和温度档位换算。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping

from .devices import FRIDGE, WATER_HEATER, DeviceSpec


@dataclass(frozen=True, slots=True)
class ClimateSpec:
    key: str
    name: str
    current_key: str
    target_key: str
    min_temp: float
    max_temp: float
    step: float
    to_display: Callable[[int], float]
    to_level: Callable[[float], int]
    icon: str
    device: DeviceSpec = FRIDGE


@dataclass(frozen=True, slots=True)
class SwitchSpec:
    key: str
    name: str
    icon: str
    device: DeviceSpec
    category: str | None = None
    on_value: Any = True
    off_value: Any = False
    unique_key: str | None = None


@dataclass(frozen=True, slots=True)
class SelectSpec:
    key: str
    name: str
    icon: str
    options: dict[Any, str]
    device: DeviceSpec
    category: str | None = None


@dataclass(frozen=True, slots=True)
class NumberSpec:
    key: str
    name: str
    icon: str
    min_value: float
    max_value: float
    step: float
    unit: str | None
    device: DeviceSpec
    category: str | None = "config"


@dataclass(frozen=True, slots=True)
class SensorSpec:
    key: str
    name: str
    icon: str
    device: DeviceSpec
    device_class: str | None = None
    unit: str | None = None
    state_class: str | None = None
    category: str | None = None
    precision: int | None = None


@dataclass(frozen=True, slots=True)
class BinarySpec:
    key: str
    name: str
    icon: str
    device: DeviceSpec
    device_class: str | None = None
    category: str | None = None
    on_value: Any = True


@dataclass(frozen=True, slots=True)
class TextSpec:
    key: str
    name: str
    icon: str
    device: DeviceSpec
    category: str | None = "config"
    max_length: int = 32


VT_ROOM_2_MODES = {
    31: "0°保鲜",
    33: "冰镇",
    35: "珍品",
    37: "母婴",
}

ZERO_COLD_WATER_MODES = {
    4: "关闭",
    5: "单次循环",
    6: "预约循环",
    7: "全程循环",
}

PRESSURIZE_MODES = {
    0: "关闭",
    1: "低档",
    2: "中档",
    3: "高档",
}

WATERFALL_MODES = {
    0: "关闭",
    1: "低档",
    2: "中档",
    3: "高档",
}

HALF_PIPE_OP_MODES = {
    0: "关闭",
    1: "半管",
}

HALF_PIPE_STATUS = {
    0: "空闲",
    1: "学习中",
    2: "已完成",
    3: "异常",
}

SCOUR_MODES = {
    **{index: f"沐浴 {index}" for index in range(1, 27)},
    **{index: f"冲洗 {index - 128}" for index in range(129, 141)},
}

FRIDGE_CLIMATES = (
    ClimateSpec(
        key="refrigerator",
        name="冷藏室",
        current_key="refrigeratorTemperatureC",
        target_key="refrigeratorTargetTempLevel",
        min_temp=1,
        max_temp=9,
        step=1,
        to_display=lambda level: level - 1,
        to_level=lambda display: int(round(display)) + 1,
        icon="mdi:fridge-outline",
    ),
    ClimateSpec(
        key="freezer",
        name="冷冻室",
        current_key="freezerTemperatureC",
        target_key="freezerTargetTempLevel",
        min_temp=-24,
        max_temp=-14,
        step=1,
        to_display=lambda level: level - 30,
        to_level=lambda display: int(round(display)) + 30,
        icon="mdi:snowflake",
    ),
    ClimateSpec(
        key="vt_room",
        name="变温室",
        current_key="vtRoomTemperature",
        target_key="vtRoomTargetTempLevel",
        min_temp=-20,
        max_temp=5,
        step=1,
        to_display=lambda level: level - 31,
        to_level=lambda display: int(round(display)) + 31,
        icon="mdi:thermometer-minus",
    ),
)

SWITCHES = (
    SwitchSpec("intelligenceMode", "智能模式", "mdi:brain", FRIDGE),
    SwitchSpec("travelMode", "假日模式", "mdi:bag-suitcase", FRIDGE),
    SwitchSpec("nightMode", "夜间模式", "mdi:weather-night", FRIDGE),
    SwitchSpec("cellPreservationStatus", "细胞级保鲜", "mdi:leaf", FRIDGE),
    SwitchSpec("daypartingElectricityStatus", "分时节电", "mdi:lightning-bolt", FRIDGE),
    SwitchSpec("forcedDefrostingStatus", "强制化霜", "mdi:snowflake-melt", FRIDGE, "config"),
    SwitchSpec("emergencyPowerSaving", "紧急节电", "mdi:battery-alert", FRIDGE, "config"),
    SwitchSpec("peakPowerSaving", "峰电节电", "mdi:sine-wave", FRIDGE, "config"),
    SwitchSpec("refSterilizationForcedOn", "强制开启杀菌", "mdi:bacteria", FRIDGE, "config"),
    SwitchSpec("refSterilizationForcedOff", "强制关闭杀菌", "mdi:bacteria-outline", FRIDGE, "config"),
    SwitchSpec("purificationMode", "净化模式", "mdi:air-filter", FRIDGE, "config", on_value=3, off_value=0),
    SwitchSpec("safetyLockStatus", "安全锁", "mdi:lock", WATER_HEATER),
    SwitchSpec("energySavingStatus", "节能", "mdi:leaf", WATER_HEATER),
    SwitchSpec("ecoStatus", "ECO", "mdi:sprout", WATER_HEATER),
    SwitchSpec("smartEnergySavingStatus", "智能节能", "mdi:leaf-circle", WATER_HEATER),
    SwitchSpec("smartTempSensingStatus", "智能感温", "mdi:thermometer-auto", WATER_HEATER),
    SwitchSpec("constTempHeatStatus", "恒温加热", "mdi:thermometer-lines", WATER_HEATER),
    SwitchSpec("smartCapacityChangeStatus", "智能变升", "mdi:swap-vertical", WATER_HEATER, "config"),
    SwitchSpec("uvSterilizationStatus", "UV杀菌", "mdi:bacteria", WATER_HEATER),
    SwitchSpec("internalCirculationStatus", "内循环", "mdi:sync", WATER_HEATER),
    SwitchSpec("tankWateringStatus", "水箱上水", "mdi:bathtub", WATER_HEATER),
    SwitchSpec("autoHalfPipeLearningStatus", "半管自动学习", "mdi:pipe", WATER_HEATER, "config", on_value=1, off_value=0),
    SwitchSpec("alarmMuteStatus", "报警静音", "mdi:volume-off", WATER_HEATER, "config"),
    SwitchSpec("NFCStatus", "NFC", "mdi:nfc", WATER_HEATER, "config"),
    SwitchSpec("fanSelfCleaningStatus", "风机自清洁", "mdi:fan-clock", WATER_HEATER, "config"),
    SwitchSpec("safeSelfTestStatus", "安全自检", "mdi:shield-check", WATER_HEATER, "config"),
    SwitchSpec("voiceModuleOnOffStatus", "语音模块", "mdi:account-voice", WATER_HEATER, "config"),
    SwitchSpec("voiceModuleAutoBroadcastStatus", "语音自动播报", "mdi:bullhorn", WATER_HEATER, "config"),
    SwitchSpec("voiceModuleWakeStatus", "语音唤醒", "mdi:microphone", WATER_HEATER, "config"),
    SwitchSpec(
        "zeroColdWaterMode",
        "零冷水单次循环",
        "mdi:water-sync",
        WATER_HEATER,
        on_value=5,
        off_value=4,
        unique_key="zeroColdWaterMode_single",
    ),
    SwitchSpec(
        "zeroColdWaterMode",
        "零冷水预约循环",
        "mdi:calendar-clock",
        WATER_HEATER,
        on_value=6,
        off_value=4,
        unique_key="zeroColdWaterMode_book",
    ),
    SwitchSpec(
        "zeroColdWaterMode",
        "零冷水全程循环",
        "mdi:infinity",
        WATER_HEATER,
        on_value=7,
        off_value=4,
        unique_key="zeroColdWaterMode_always",
    ),
)

SELECTS = (
    SelectSpec("vtRoom2TargetTempLevel", "第二变温室", "mdi:snowflake-thermometer", VT_ROOM_2_MODES, FRIDGE),
    SelectSpec("pressurizeMode", "增压模式", "mdi:gauge", PRESSURIZE_MODES, WATER_HEATER),
    SelectSpec("waterfallMode", "瀑布浴", "mdi:waterfall", WATERFALL_MODES, WATER_HEATER),
    SelectSpec("halfPipeOpModeSet", "半管运行模式", "mdi:pipe-valve", HALF_PIPE_OP_MODES, WATER_HEATER, "config"),
    SelectSpec("scourState", "沐浴档位", "mdi:shower-head", SCOUR_MODES, WATER_HEATER, "config"),
)

NUMBERS = (
    NumberSpec("brightness", "显示亮度", "mdi:brightness-percent", 1, 100, 1, "%", FRIDGE),
    NumberSpec("modeBrightness", "夜间模式亮度", "mdi:brightness-6", 1, 50, 1, "%", FRIDGE),
    NumberSpec("tankTargetTemp", "水箱目标温度", "mdi:bathtub", 0, 70, 1, "°C", WATER_HEATER, None),
    NumberSpec("tankTargetFlux", "水箱目标水量", "mdi:cup-water", 0, 990, 10, "L", WATER_HEATER, None),
    NumberSpec("internalCirculationBookTime", "内循环预约时长", "mdi:timer-outline", 0, 50, 1, "min", WATER_HEATER),
    NumberSpec("singleResnTime", "单次预约时长", "mdi:timer-outline", 0, 50, 1, "min", WATER_HEATER),
    NumberSpec("silentResnTime", "静音预约时长", "mdi:timer-sand", 0, 30, 1, "min", WATER_HEATER),
    NumberSpec("halfPipeLearningTime", "半管学习时间", "mdi:timer", 0, 1800, 1, "s", WATER_HEATER),
    NumberSpec("halfPipeTimeSet", "半管循环时间", "mdi:timer-sync", 0, 1800, 1, "s", WATER_HEATER),
    NumberSpec("ecoJudgeTemp", "节能判断温度", "mdi:thermometer", 0, 35, 0.1, "°C", WATER_HEATER),
    NumberSpec("pumpAntifreezeTemperature", "水泵防冻温度", "mdi:snowflake-thermometer", 0, 10, 1, "°C", WATER_HEATER),
    NumberSpec("voiceModuleVolume", "语音音量", "mdi:volume-high", 0, 255, 1, None, WATER_HEATER),
)

TEXTS = (
    TextSpec("lightModeStartTime", "夜间模式开始时间", "mdi:clock-start", FRIDGE),
    TextSpec("lightModeStopTime", "夜间模式结束时间", "mdi:clock-end", FRIDGE),
    TextSpec("sharingElectricityStartTime", "分时节电开始时间", "mdi:clock-start", FRIDGE),
    TextSpec("sharingElectricityEndTime", "分时节电结束时间", "mdi:clock-end", FRIDGE),
)

SENSORS = (
    SensorSpec("refrigeratorTemperatureC", "冷藏室温度", "mdi:thermometer", FRIDGE, "temperature", "°C", "measurement"),
    SensorSpec("freezerTemperatureC", "冷冻室温度", "mdi:thermometer", FRIDGE, "temperature", "°C", "measurement"),
    SensorSpec("vtRoomTemperature", "变温室温度", "mdi:thermometer", FRIDGE, "temperature", "°C", "measurement"),
    SensorSpec("envTemperature", "环境温度", "mdi:home-thermometer", FRIDGE, "temperature", "°C", "measurement"),
    SensorSpec("envHumidity", "环境湿度", "mdi:water-percent", FRIDGE, "humidity", "%", "measurement"),
    SensorSpec("sterilizationTime", "杀菌进度", "mdi:progress-clock", FRIDGE, None, "%", None, "diagnostic"),
    SensorSpec("refSterilizationOffTime", "杀菌剩余停用时间", "mdi:timer-sand", FRIDGE, "duration", "min", None, "diagnostic"),
    SensorSpec("inWaterTemp", "进水温度", "mdi:thermometer-water", WATER_HEATER, "temperature", "°C", "measurement"),
    SensorSpec("backWaterTemp", "回水温度", "mdi:thermometer-chevron-down", WATER_HEATER, "temperature", "°C", "measurement"),
    SensorSpec("indoorTemperature", "室内温度", "mdi:home-thermometer", WATER_HEATER, "temperature", "°C", "measurement"),
    SensorSpec("tankCurrentFlux", "水箱当前水量", "mdi:cup-water", WATER_HEATER, None, "L", "measurement"),
    SensorSpec("halfPipeLearningStatus", "半管学习状态", "mdi:pipe", WATER_HEATER, None, None, None, "diagnostic"),
    SensorSpec("curWaterFlux", "当前水流量", "mdi:water", WATER_HEATER, None, "L/min", "measurement"),
    SensorSpec("realTimePowerPct", "实时功率", "mdi:lightning-bolt", WATER_HEATER, None, "%", "measurement"),
    SensorSpec("runFanSpd", "风机转速", "mdi:fan", WATER_HEATER, None, "RPM", "measurement", "diagnostic"),
    SensorSpec("coValue", "一氧化碳", "mdi:molecule-co", WATER_HEATER, "carbon_monoxide", "ppm", "measurement", "diagnostic"),
    SensorSpec("ch4Value", "甲烷", "mdi:molecule", WATER_HEATER, None, "ppm", "measurement", "diagnostic"),
    SensorSpec("ratedPower", "额定能力", "mdi:gauge", WATER_HEATER, None, "L", None, "diagnostic"),
)

BINARY_SENSORS = (
    BinarySpec("refrigeratorDoorStatus", "冷藏室门", "mdi:door", FRIDGE, "door"),
    BinarySpec("refrigerator2DoorStatus", "第二冷藏室门", "mdi:door", FRIDGE, "door"),
    BinarySpec("freezerDoorStatus", "冷冻室门", "mdi:door", FRIDGE, "door"),
    BinarySpec("vtRoomDoorStatus", "变温室门", "mdi:door", FRIDGE, "door"),
    BinarySpec("refSterilizationModuleStatus", "杀菌模块", "mdi:bacteria-outline", FRIDGE, None, "diagnostic"),
    BinarySpec("flameStatus", "火焰", "mdi:fire", WATER_HEATER, None),
    BinarySpec("fanStatus", "风机", "mdi:fan", WATER_HEATER, None, "diagnostic"),
    BinarySpec("flowStatus", "水流", "mdi:water-pump", WATER_HEATER, None),
    BinarySpec("waterUsedStatus", "正在用水", "mdi:shower", WATER_HEATER, None),
    BinarySpec("tankWaterLevel", "水箱水位到位", "mdi:water-check", WATER_HEATER, None),
    BinarySpec("pipeAntifreezingStatus", "管道防冻", "mdi:snowflake-alert", WATER_HEATER, None, "diagnostic"),
    BinarySpec("cycAntifreezingStatus", "循环防冻", "mdi:snowflake-check", WATER_HEATER, None, "diagnostic"),
)

WATER_HEATER_EXTRAS = (
    "inWaterTemp",
    "backWaterTemp",
    "indoorTemperature",
    "zeroColdWaterTargetTemp",
    "curWaterFlux",
    "realTimePowerPct",
    "realTimePower",
    "ratedPower",
    "runFanSpd",
    "pwm",
    "flameStatus",
    "fanStatus",
    "flowStatus",
    "waterUsedStatus",
    "userWaterBurnTime",
    "coValue",
    "ch4Value",
    "zeroColdWaterMode",
    "zeroColdWaterStatus",
    "zeroColdWaterFuncExist",
    "pressurizeMode",
    "pressurizeSupported",
    "waterfallMode",
    "safetyLockStatus",
    "energySavingStatus",
    "ecoStatus",
    "smartEnergySavingStatus",
    "internalCirculationStatus",
    "discaleStatus",
    "selfTestStatus",
    "valveStatus",
    "ctrPriority",
    "timeHH",
    "timeMM",
    "week",
)

LABELS: dict[str, str] = {
    "refrigerator2DoorStatus": "第二冷藏室门",
    "refrigeratorTargetTempLevel": "冷藏目标温度档位",
    "freezerTargetTempLevel": "冷冻目标温度档位",
    "vtRoomTargetTempLevel": "变温室目标温度档位",
    "vtRoom2TargetTempLevel": "第二变温室模式",
    "intelligenceMode": "智能模式",
    "vtRoomDoorStatus": "变温室门",
    "refrigeratorDoorStatus": "冷藏室门",
    "freezerDoorStatus": "冷冻室门",
    "refSterilizationModuleStatus": "杀菌模块",
    "refSterilizationForcedOff": "强制关闭杀菌",
    "refSterilizationForcedOn": "强制开启杀菌",
    "refSterilizationOffTime": "杀菌剩余停用时间",
    "sterilizationTime": "杀菌进度",
    "lightModeStopTime": "夜间模式结束时间",
    "lightModeStartTime": "夜间模式开始时间",
    "modeBrightness": "夜间模式亮度",
    "freezerTemperatureC": "冷冻室当前温度",
    "brightness": "显示亮度",
    "travelMode": "假日模式",
    "vtRoomTemperature": "变温室当前温度",
    "nightMode": "夜间模式",
    "refrigeratorTemperatureC": "冷藏室当前温度",
    "envTemperature": "环境温度",
    "cellPreservationStatus": "细胞级保鲜",
    "envHumidity": "环境湿度",
    "daypartingElectricityStatus": "分时节电",
    "sharingElectricityStartTime": "分时节电开始时间",
    "sharingElectricityEndTime": "分时节电结束时间",
    "smartGridfunctions": "智能电网功能",
    "forcedDefrostingStatus": "强制化霜",
    "emergencyPowerSaving": "紧急节电",
    "peakPowerSaving": "峰电节电",
    "purificationSupported": "支持净化",
    "purificationMode": "净化模式",
    "outWaterTemp": "出水温度",
    "inWaterTemp": "进水温度",
    "backWaterTemp": "回水温度",
    "targetTemp": "淋浴目标温度",
    "tankTargetTemp": "水箱目标温度",
    "zeroColdWaterTargetTemp": "零冷水目标温度",
    "runFanSpd": "风机转速",
    "pwm": "风机PWM",
    "ratedPower": "额定能力",
    "tankTargetFlux": "水箱目标水量",
    "realTimePowerPct": "实时功率百分比",
    "curWaterFlux": "当前水流量",
    "tankCurrentFlux": "水箱当前水量",
    "coValue": "一氧化碳浓度",
    "ch4Value": "甲烷浓度",
    "singleResnTime": "单次预约时长",
    "userWaterBurnTime": "本次燃烧时长",
    "tankWateringStatus": "水箱上水",
    "tankWaterLevel": "水箱水位到位",
    "alarmMuteStatus": "报警静音",
    "alarmDetectionStatus": "报警检测中",
    "constTempHeatStatus": "恒温加热",
    "pressurizeSupported": "支持增压",
    "smartTempSensingStatus": "智能感温",
    "energySavingStatus": "节能",
    "safetyLockStatus": "安全锁",
    "burnTime1HourRemindStatus": "燃烧满1小时提醒",
    "flowStatus": "有水流",
    "fanStatus": "风机运转",
    "flameStatus": "有火焰",
    "onOffStatus": "开关",
    "cloudSmartRunningStatus": "云智能运行中",
    "waterUsedStatus": "正在用水",
    "altitudeAdaptationStatus": "海拔自适应",
    "ctrPriority": "控制优先级",
    "prtlVersion": "协议版本",
    "zeroColdWaterFuncExist": "具备零冷水功能",
    "selfTestStatus": "自检中",
    "valveStatus": "燃气阀状态",
    "tankCode": "水箱编码",
    "showerCode": "花洒编码",
    "scourState": "沐浴档位",
    "ecoStatus": "ECO",
    "alarmModuleExist": "具备报警模块",
    "NFCStatus": "NFC",
    "smartEnergySavingStatus": "智能节能",
    "smartCapacityChangeStatus": "智能变升",
    "uvSterilizationStatus": "UV杀菌",
    "fanSelfCleaningStatus": "风机自清洁",
    "safeSelfTestStatus": "安全自检",
    "pipeAntifreezingStatus": "管道防冻",
    "cycAntifreezingStatus": "循环防冻",
    "cycFuncSelect": "循环功能选择",
    "pumpRunningStatus": "水泵运行状态",
    "waterCycleFinish": "水循环完成",
    "singleCycleFinish": "单次循环完成",
    "highTempRemindStatus": "高温提醒",
    "netCfgStatus": "配网状态",
    "discaleStatus": "除垢状态",
    "burnTimeHalfHourRemindStatus": "燃烧满半小时提醒",
    "userSceneFuncCode": "用户场景功能码",
    "timeHH": "时钟-时",
    "timeMM": "时钟-分",
    "zeroColdWaterMode": "零冷水模式",
    "week": "星期",
    "ecoJudgeTemp": "节能判断温度",
    "realTimePower": "实时能力",
    "indoorTemperature": "室内温度",
    "waterfallMode": "瀑布浴模式",
    "pressurizeMode": "增压模式",
    "voiceModuleVolume": "语音音量",
    "voiceModuleAutoBroadcastStatus": "语音自动播报",
    "voiceModuleBroadcastStatus": "语音播报中",
    "voiceModuleWakeStatus": "语音唤醒",
    "voiceModuleOnOffStatus": "语音模块开关",
    "voiceModuleErrCode": "语音模块错误码",
    "voiceCommandNumber": "语音命令编号",
    "totalWorkTime": "累计工作时间",
    "totalUseGasL": "累计用气量",
    "totalWaterL": "累计用水量",
    "targetRatedPower": "目标额定能力",
    "curveID": "当前曲线ID",
    "dateYY": "日期-年",
    "dateMM": "日期-月",
    "dateDD": "日期-日",
    "zeroColdWaterStatus": "零冷水状态",
    "internalCirculationStatus": "内循环开关",
    "internalCirculationPumpStatus": "内循环泵状态",
    "internalCirculationBookTime": "内循环预约时长",
    "halfPipeLearningTime": "半管学习时间",
    "halfPipeTimeSet": "半管循环时间",
    "halfPipeOpModeSet": "半管运行模式",
    "autoHalfPipeLearningStatus": "半管自动学习",
    "halfPipeLearningStatus": "半管学习状态",
    "pumpAntifreezeTemperature": "水泵防冻温度",
    "zcwTimingCycleStatus": "零冷水定时循环",
    "compressor1Frequency": "压缩机频率",
    "refrigeratorFanStatus": "冷藏风机状态",
    "freezerFanStatus": "冷冻风机状态",
    "coolingFanStatus": "冷凝风机状态",
}

ALARM_LABELS: dict[str, str] = {
    "vtRoomDefrostingSensorErr": "变温室化霜传感器故障",
    "ctrBoardCommErr": "控制板通信故障",
    "freezerDoorAlarm": "冷冻室门报警",
    "envTempSensorErr": "环境温度传感器故障",
    "refrigeratorSensorErr": "冷藏室传感器故障",
    "refrigeratorDefrostingSensorErr": "冷藏化霜传感器故障",
    "refrigeratorFanErr": "冷藏风机故障",
    "dryAreaSensorErr": "干区传感器故障",
    "freezerFanErr": "冷冻风机故障",
    "vtRoomDefrostingErr": "变温室化霜故障",
    "refrigeratorDoorAlarm": "冷藏室门报警",
    "o3ModuleOnErr": "臭氧模块开启故障",
    "freezerSensorErr": "冷冻室传感器故障",
    "o3ModuleOffErr": "臭氧模块关闭故障",
    "refrigeratorDefrostingErr": "冷藏化霜故障",
    "iicCommErr": "IIC通信故障",
    "vtRoomDoorAlarm": "变温室门报警",
    "solenoidValvesErr": "电磁阀故障",
    "vtRoomFanErr": "变温室风机故障",
    "freezerDefrostingSensorErr": "冷冻化霜传感器故障",
    "freezerDefrostingErr": "冷冻化霜故障",
    "refrigerator2DoorAlarm": "第二冷藏室门报警",
    "coolingFanErr": "冷凝风机故障",
    "airDoor2Err": "风门2故障",
    "humiditySensorErr": "湿度传感器故障",
    "vtRoomSensorErr": "变温室传感器故障",
    "ignitionFailAlarm": "点火失败",
    "flameoutAlarm": "意外熄火",
    "fanErr": "风机故障",
    "overHeatAlarm": "过热保护",
    "TempSensorErr": "温度传感器故障",
    "dryHeatingAlarm": "干烧保护",
    "displayBoardCommunicationErr": "显示板通信故障",
    "pcCommunicationErr": "主控通信故障",
    "dialSwitchErr": "拨码开关故障",
    "memoryChipErr": "存储器故障",
    "exhaustPlugErr": "烟道堵塞",
    "backwaterTempSensorErr": "回水温度传感器故障",
    "waterPumpErr": "水泵故障",
    "windPressureSwitchErr": "风压开关故障",
    "gasDensityOverHighAlarm": "燃气浓度过高",
    "alarmSensorErr": "报警传感器故障",
    "waterServoErr": "水伺服故障",
    "ch4ExceedAlarm": "甲烷超标",
    "ch4SensorErr": "甲烷传感器故障",
    "alarmCommunicationErr": "报警模块通信故障",
    "volumeCodeErr": "能力编码故障",
    "drainPipeBlockAlarm": "排水管堵塞",
    "plcCommErr": "PLC通信故障",
    "valveErr": "阀体故障",
    "clockChipErr": "时钟芯片故障",
    "leakageAlarm": "漏气报警",
    "wifiCommunicationErr": "WiFi通信故障",
    "circPumpAntifreezingErr": "循环泵防冻故障",
}

_SCHEDULE_HOURS = (
    ("defWorkHour", "默认工作日时段"),
    ("defRestHour", "默认休息日时段"),
    ("workHour", "工作日时段"),
    ("restHour", "休息日时段"),
    ("oyWorkHour", "仅一次工作日时段"),
    ("oyRestHour", "仅一次休息日时段"),
    ("allWorkHour", "全部工作日时段"),
    ("allRestHour", "全部休息日时段"),
)
_SCHEDULE_DAYS = (
    ("defWorkDay", "默认工作日"),
    ("workDay", "工作日"),
    ("oyWorkDay", "仅一次工作日"),
    ("allWorkDay", "全部工作日"),
)
_DAY_SUFFIX = {
    "Mon": "周一",
    "Tue": "周二",
    "Wed": "周三",
    "Thu": "周四",
    "Fri": "周五",
    "Sat": "周六",
    "Sun": "周日",
}

_CLAIMED: dict[str, set[str]] = {}


def _claimed_for(device_key: str) -> set[str]:
    claimed = _CLAIMED.get(device_key)
    if claimed is not None:
        return claimed
    keys: set[str] = {
        "_alarms",
        "_has_alarm",
        "_alarm_raw",
        "_detail",
        "onOffStatus",
        "targetTemp",
        "outWaterTemp",
    }
    for item in FRIDGE_CLIMATES:
        if item.device.key == device_key:
            keys.update((item.current_key, item.target_key))
    for collection in (SWITCHES, SELECTS, NUMBERS, SENSORS, BINARY_SENSORS, TEXTS):
        for item in collection:
            if item.device.key == device_key:
                keys.add(item.key)
    _CLAIMED[device_key] = keys
    return keys


def label(name: str) -> str:
    return LABELS.get(name) or ALARM_LABELS.get(name) or name


def icon_for(name: str, default: str = "mdi:information-outline") -> str:
    key = name.lower()
    if "temp" in key:
        return "mdi:thermometer"
    if "humid" in key:
        return "mdi:water-percent"
    if "door" in key:
        return "mdi:door"
    if "flame" in key or "burn" in key:
        return "mdi:fire"
    if "fan" in key:
        return "mdi:fan"
    if "lock" in key:
        return "mdi:lock"
    if "eco" in key or "energy" in key or "saving" in key:
        return "mdi:leaf"
    if "water" in key or "flux" in key or "shower" in key:
        return "mdi:water"
    if "ch4" in key or "methane" in key:
        return "mdi:molecule"
    if key.startswith("co") and "cold" not in key:
        return "mdi:molecule-co"
    if "night" in key or "lightmode" in key:
        return "mdi:weather-night"
    if "travel" in key or "holiday" in key:
        return "mdi:bag-suitcase"
    if "steril" in key or "uv" in key or "bacteria" in key:
        return "mdi:bacteria"
    if "bright" in key:
        return "mdi:brightness-6"
    if "alarm" in key:
        return "mdi:alarm-light"
    if "power" in key:
        return "mdi:lightning-bolt"
    if "nfc" in key:
        return "mdi:nfc"
    if "voice" in key:
        return "mdi:account-voice"
    if "pressur" in key:
        return "mdi:gauge"
    if "intelligent" in key or "smart" in key:
        return "mdi:brain"
    if "preservation" in key or "cell" in key:
        return "mdi:leaf"
    if "defrost" in key:
        return "mdi:snowflake-melt"
    if "purif" in key:
        return "mdi:air-filter"
    if "lock" in key:
        return "mdi:lock"
    return default


def _is_schedule_field(name: str) -> bool:
    if any(name.startswith(prefix) for prefix, _ in _SCHEDULE_HOURS):
        return True
    return any(name.startswith(prefix) for prefix, _ in _SCHEDULE_DAYS)


def _compress_hours(values: Mapping[str, Any], prefix: str) -> str:
    hours = [str(hour) for hour in range(24) if values.get(f"{prefix}{hour}")]
    return ",".join(hours) if hours else "无"


def _compress_days(values: Mapping[str, Any], prefix: str) -> str:
    days = [label for suffix, label in _DAY_SUFFIX.items() if values.get(f"{prefix}{suffix}")]
    return ",".join(days) if days else "无"


def remaining_attributes(device_key: str, values: Mapping[str, Any] | None) -> dict[str, Any]:
    """把未单独建实体的字段收进诊断属性，预约时段压缩成字符串。"""
    if not values:
        return {}
    claimed = _claimed_for(device_key)
    extras: dict[str, Any] = {}
    has_schedule = False
    for name, value in values.items():
        if name.startswith("_") or name in claimed:
            continue
        if _is_schedule_field(name):
            has_schedule = True
            continue
        extras[label(name)] = _display_value(name, value)
    if has_schedule:
        for prefix, title in _SCHEDULE_HOURS:
            extras[title] = _compress_hours(values, prefix)
        for prefix, title in _SCHEDULE_DAYS:
            extras[title] = _compress_days(values, prefix)
    return extras


def selected_attributes(values: Mapping[str, Any] | None, keys: tuple[str, ...]) -> dict[str, Any]:
    if not values:
        return {}
    return {
        label(name): _display_value(name, values[name])
        for name in keys
        if name in values
    }


def alarm_attributes(values: Mapping[str, Any] | None) -> dict[str, Any]:
    if not values:
        return {}
    active = values.get("_alarms") or {}
    names = [ALARM_LABELS.get(str(name), str(name)) for name, flag in active.items() if flag]
    result: dict[str, Any] = {"活动报警": "、".join(names) if names else "无"}
    if values.get("_alarm_raw"):
        result["原始位图"] = values["_alarm_raw"]
    return result


def _display_value(name: str, value: Any) -> Any:
    if name == "vtRoom2TargetTempLevel":
        try:
            return VT_ROOM_2_MODES.get(int(value), value)
        except (TypeError, ValueError):
            return value
    if name == "zeroColdWaterMode":
        try:
            return ZERO_COLD_WATER_MODES.get(int(value), value)
        except (TypeError, ValueError):
            return value
    if name == "pressurizeMode":
        try:
            return PRESSURIZE_MODES.get(int(value), value)
        except (TypeError, ValueError):
            return value
    if name == "waterfallMode":
        try:
            return WATERFALL_MODES.get(int(value), value)
        except (TypeError, ValueError):
            return value
    if name == "halfPipeOpModeSet":
        try:
            return HALF_PIPE_OP_MODES.get(int(value), value)
        except (TypeError, ValueError):
            return value
    if name == "halfPipeLearningStatus":
        try:
            return HALF_PIPE_STATUS.get(int(value), value)
        except (TypeError, ValueError):
            return value
    if name == "scourState":
        try:
            return SCOUR_MODES.get(int(value), value)
        except (TypeError, ValueError):
            return value
    if isinstance(value, bool):
        return "开" if value else "关"
    return value


def option_value(spec: SelectSpec, option: str) -> Any:
    for raw, text in spec.options.items():
        if text == option:
            return raw
    raise ValueError(option)
