
import plotly.graph_objects as go
import plotly.io as pio
import os
import base64
from io import BytesIO


def generate_performance_chart(performance_data):

    if not performance_data:
        return None

    dates = [entry['date'] for entry in performance_data]
    values = [entry['value'] for entry in performance_data]
    deposits = [entry['deposits'] for entry in performance_data]
    returns = [entry['returns'] for entry in performance_data]

    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=dates,
        y=values,
        mode='lines',
        name='Portfolio Value',
        line=dict(color='#0d6efd', width=2)
    ))

    fig.add_trace(go.Scatter(
        x=dates,
        y=deposits,
        mode='lines',
        name='Net Deposits',
        line=dict(color='#dc3545', width=2, dash='dash')
    ))

    fig.add_trace(go.Scatter(
        x=dates,
        y=returns,
        mode='lines',
        name='Returns',
        line=dict(color='#198754', width=2)
    ))

    # Layout
    fig.update_layout(
        title='Portfolio Performance Over Time',
        xaxis_title='Date',
        yaxis_title='Amount ($)',
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="center",
            x=0.5
        ),
        template='plotly_white',
        height=400,
        margin=dict(l=50, r=50, t=80, b=50)
    )

    img_bytes = pio.to_image(fig, format='png')
    img_base64 = base64.b64encode(img_bytes).decode('ascii')

    return img_base64


def generate_sector_chart(sector_data):
    if not sector_data:
        return None

    sectors = [item['sector'] for item in sector_data]
    values = [item['value'] for item in sector_data]
    colors = ['#0d6efd', '#6610f2', '#6f42c1', '#d63384', '#dc3545',
              '#fd7e14', '#ffc107', '#198754', '#20c997', '#0dcaf0']
    if len(sectors) > len(colors):
        colors = colors * (len(sectors) // len(colors) + 1)

    fig = go.Figure(data=[go.Pie(
        labels=sectors,
        values=values,
        hole=.4,
        marker_colors=colors[:len(sectors)]
    )])

    fig.update_layout(
        title='Sector Allocation',
        showlegend=True,
        legend=dict(
            orientation="v",
            yanchor="middle",
            y=0.5,
            xanchor="right",
            x=1.1
        ),
        height=500,
        margin=dict(l=50, r=100, t=80, b=50)
    )
    img_bytes = pio.to_image(fig, format='png')
    img_base64 = base64.b64encode(img_bytes).decode('ascii')

    return img_base64
