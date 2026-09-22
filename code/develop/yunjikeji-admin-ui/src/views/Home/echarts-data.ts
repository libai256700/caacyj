import type { EChartsOption } from 'echarts'

export interface ChartPoint {
  name: string
  value: number
}

export interface PracticeChartItem {
  name: string
  value: number
}

const emptyGraphic = (hasData: boolean) =>
  hasData
    ? []
    : {
        type: 'text',
        left: 'center',
        top: 'middle',
        style: {
          text: '暂无数据',
          fill: '#909399',
          fontSize: 14
        }
      }

export const createLineChartOptions = (
  title: string,
  seriesName: string,
  points: ChartPoint[],
  color: string
): EChartsOption => {
  const hasData = points.some((item) => item.value > 0)
  return {
    color: [color],
    grid: {
      left: 16,
      right: 20,
      top: 42,
      bottom: 18,
      containLabel: true
    },
    tooltip: {
      trigger: 'axis'
    },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: points.map((item) => item.name),
      axisTick: {
        show: false
      }
    },
    yAxis: {
      type: 'value',
      minInterval: 1,
      splitLine: {
        lineStyle: {
          type: 'dashed'
        }
      }
    },
    graphic: emptyGraphic(hasData),
    series: [
      {
        name: seriesName || title,
        type: 'line',
        smooth: true,
        symbol: 'circle',
        symbolSize: 6,
        areaStyle: {
          opacity: 0.12
        },
        data: points.map((item) => item.value)
      }
    ]
  }
}

export const createPracticeChartOptions = (
  title: string,
  items: PracticeChartItem[]
): EChartsOption => {
  const hasData = items.some((item) => item.value > 0)
  return {
    color: ['#16a34a', '#dc2626', '#2563eb', '#f59e0b', '#7c3aed'],
    grid: {
      left: 16,
      right: 24,
      top: 38,
      bottom: 18,
      containLabel: true
    },
    tooltip: {
      trigger: 'axis',
      axisPointer: {
        type: 'shadow'
      }
    },
    xAxis: {
      type: 'category',
      data: items.map((item) => item.name),
      axisTick: {
        show: false
      }
    },
    yAxis: {
      type: 'value',
      minInterval: 1,
      splitLine: {
        lineStyle: {
          type: 'dashed'
        }
      }
    },
    graphic: emptyGraphic(hasData),
    series: [
      {
        name: title,
        type: 'bar',
        barMaxWidth: 48,
        data: items.map((item) => item.value)
      }
    ]
  }
}

export const lineOptions = createLineChartOptions('趋势分析', '数量', [], '#2563eb')

export const barOptions = createPracticeChartOptions('周活跃量', [])

export const pieOptions: EChartsOption = {
  color: ['#2563eb', '#16a34a', '#f59e0b', '#dc2626', '#7c3aed'],
  tooltip: {
    trigger: 'item'
  },
  legend: {
    orient: 'vertical',
    left: 'left',
    data: []
  },
  graphic: emptyGraphic(false),
  series: [
    {
      name: '用户来源',
      type: 'pie',
      radius: '55%',
      center: ['50%', '58%'],
      data: []
    }
  ]
}
