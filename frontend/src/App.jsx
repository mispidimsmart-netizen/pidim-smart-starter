import React, { useEffect, useMemo, useState } from 'react'
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, Tooltip, Legend, LabelList } from 'recharts'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

function useReports(){
  const [data, setData] = useState({ loan: [], poultry: [], grants: [] })
  const [loading, setLoading] = useState(true)
  useEffect(()=>{
    fetch(`${API_BASE}/reports/fixed`).then(r=>r.json()).then(setData).finally(()=>setLoading(false))
  },[])
  return { ...data, loading }
}

function DataTable({title, rows, columns, subtitle, showFooterTotals=true}){
  if(!rows?.length) return <div>No data</div>
  const totals = useMemo(()=>{
    const t = {}
    columns.forEach(c=>{
      if(c.total && typeof rows[0][c.key] === 'number'){
        t[c.key] = rows.reduce((s,r)=> s + (Number(r[c.key])||0), 0)
      }
    })
    return t
  },[rows, columns])

  return (
    <div>
      <h2>{title}</h2>
      {subtitle ? <div style={{marginTop:-8, marginBottom:8, color:'#334155'}}>{subtitle}</div> : null}
      <table>
        <thead>
          <tr>{columns.map(c=><th key={c.key}>{c.header}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((r,i)=> (
            <tr key={i} style={{background: String(r['Branch Name']).endsWith(' Total') ? '#fffbe6' : (r['Branch Name']==='Grand Total' ? '#dcfce7' : undefined), fontWeight: r['Branch Name']==='Grand Total' ? 800 : undefined}}>
              {columns.map(c=> <td key={c.key}>{c.format? c.format(r[c.key]) : r[c.key]}</td>)}
            </tr>
          ))}
        </tbody>
        {showFooterTotals && Object.keys(totals).length ? (
          <tfoot>
            <tr>
              {columns.map(c=> <td key={c.key}>{c.total ? (c.format? c.format(totals[c.key]) : totals[c.key]) : ''}</td>)}
            </tr>
          </tfoot>
        ) : null}
      </table>
    </div>
  )
}

function NumberFmt(n){ return (n??0).toLocaleString() }

export default function App(){
  const { loan, poultry, grants, loading } = useReports()

  const [loanCustomRows, setLoanCustomRows] = useState(null)
  const [loanMonth, setLoanMonth] = useState("")
  const [loanMonthLabel, setLoanMonthLabel] = useState("")

  if(loading) return <div className="wrap">Loading...</div>

  // Which loan rows to show (custom or fixed)
  const loanRows = loanCustomRows ?? loan
  const loanBase = loanRows.filter(r => !String(r['Branch Name']).endsWith(' Total') && r['Branch Name']!=='Grand Total' && r['Types of Loan'])
  const loanChartData = loanBase.map(r=>({ branch: r['Branch Name'], type: r['Types of Loan'], amount: Number(r['Amount of Loan']||0) }))

  const birdsBase = poultry.filter(r => r['Branch Name']!=='Grand Total')
  const birdsChartData = birdsBase.map(r=>({ branch: r['Branch Name'], type: r['Types of Poultry Rearing'], birds: Number(r['# of Birds']||0) }))

  const grantsBase = grants.filter(r => r['Branch Name']!=='Grand Total')
  const grantsChartData = grantsBase.map(r=>({ branch: r['Branch Name'], amount: Number(r['Amounts of Grants']||0) }))

  async function applyLoanMonth(){
    try{
      const url = new URL(`${API_BASE}/reports/loan`)
      if(loanMonth) url.searchParams.set("month", loanMonth)
      const resp = await fetch(url).then(r=>r.json())
      setLoanCustomRows(resp.rows || [])
      setLoanMonthLabel(resp.month_label || "")
    }catch(e){
      console.error(e)
      setLoanCustomRows(null)
      setLoanMonthLabel("")
    }
  }

  function clearLoanMonth(){
    setLoanMonth("")
    setLoanCustomRows(null)
    setLoanMonthLabel("")
  }

  return (
    <div className="wrap">

      <div className="grid">
        <div>
          {/* Custom Month Controls */}
          <div style={{display:'flex', gap:8, alignItems:'center', marginBottom:8}}>
            <label><b>Custom (Month):</b></label>
            <input type="month" value={loanMonth} onChange={e=>setLoanMonth(e.target.value)} />
            <button onClick={applyLoanMonth} style={{background:'#16a34a', color:'#fff', border:0, borderRadius:6, padding:'6px 10px', fontWeight:700}}>Apply</button>
            {loanCustomRows && <button onClick={clearLoanMonth} style={{background:'#e11d48', color:'#fff', border:0, borderRadius:6, padding:'6px 10px', fontWeight:700}}>Clear</button>}
          </div>

          <DataTable
            title="📊 Branch Wise Loan Disbursement"
            subtitle={loanMonthLabel ? `Month: ${loanMonthLabel}` : undefined}
            rows={loanRows}
            showFooterTotals={false}  {/* no extra sums footer */}
            columns={[
              {key:'Sl No', header:'Sl No'},
              {key:'Branch Name', header:'Branch Name'},
              {key:'Types of Loan', header:'Types of Loan'},
              {key:'# of Loan', header:'# of Loan', total:true, format:NumberFmt},
              {key:'Amount of Loan', header:'Amount of Loan', total:true, format:NumberFmt},
            ]}
          />
        </div>

        <div>
          <h2>Loan — Visualization</h2>
          <ResponsiveContainer width="100%" height={380}>
            <BarChart data={loanChartData}>
              <XAxis dataKey="branch" hide />
              <YAxis />
              <Tooltip />
              <Legend />
              <Bar dataKey="amount" name="Amount of Loan" fill="#16a34a">
                <LabelList dataKey="amount" position="top" formatter={NumberFmt} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="grid">
        <DataTable
          title="🐔 Types of Poultry Rearing"
          rows={poultry}
          columns={[
            {key:'Sl No', header:'Sl No'},
            {key:'Branch Name', header:'Branch Name'},
            {key:'Types of Poultry Rearing', header:'Types of Poultry Rearing'},
            {key:'# of MEs', header:'# of MEs', total:true, format:NumberFmt},
            {key:'# of Birds', header:'# of Birds', total:true, format:NumberFmt},
          ]}
        />
        <div>
          <h2>Poultry — Visualization</h2>
          <ResponsiveContainer width="100%" height={380}>
            <BarChart data={birdsChartData}>
              <XAxis dataKey="branch" hide />
              <YAxis />
              <Tooltip />
              <Legend />
              <Bar dataKey="birds" name="# of Birds" fill="#0ea5e9">
                <LabelList dataKey="birds" position="top" formatter={NumberFmt} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div className="grid">
        <DataTable
          title="💠 MEs Grants Information"
          rows={grants}
          columns={[
            {key:'Sl No', header:'Sl No'},
            {key:'Branch Name', header:'Branch Name'},
            {key:'Number on MEs', header:'Number on MEs', total:true, format:NumberFmt},
            {key:'Amounts of Grants', header:'Amounts of Grants', total:true, format:NumberFmt},
          ]}
        />
        <div>
          <h2>Grants — Visualization</h2>
          <ResponsiveContainer width="100%" height={380}>
            <BarChart data={grantsChartData}>
              <XAxis dataKey="branch" hide />
              <YAxis />
              <Tooltip />
              <Legend />
              <Bar dataKey="amount" name="Amount of Grants" fill="#f59e0b">
                <LabelList dataKey="amount" position="top" formatter={NumberFmt} />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      <div style={{marginTop: 24}}>
        <a href={`${API_BASE}/export/excel`} target="_blank" rel="noreferrer">
          <button style={{background:'#16a34a', color:'#fff', border:0, borderRadius:8, padding:'10px 14px', fontWeight:700}}>⬇️ Download All (Excel)</button>
        </a>
      </div>
    </div>
  )
}
