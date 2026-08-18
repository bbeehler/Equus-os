'use client'
import { useEffect, useState } from 'react'
import { supabase } from '@/lib/supabase'
import { calculateTravelFee } from '@/lib/logistics'
import Link from 'next/link'

export default function BookingPage() {
  const [horses, setHorses] = useState<any[]>([])
  const [zones, setZones] = useState<any[]>([])
  const [appointments, setAppointments] = useState<any[]>([])

  const [selectedHorseId, setSelectedHorseId] = useState('')
  const [bookingDate, setBookingDate] = useState('')
  const [distanceKm, setDistanceKm] = useState<number>(35)

  useEffect(() => {
    loadData()
  }, [])

  async function loadData() {
    const { data: horsesData } = await supabase.from('horses').select('*, barns(*)')
    const { data: zonesData } = await supabase.from('route_zones').select('*')
    const { data: apptsData } = await supabase.from('appointments').select('*, horses(*, barns(*))').order('appointment_date', { ascending: true })

    if (horsesData) setHorses(horsesData)
    if (zonesData) setZones(zonesData)
    if (apptsData) setAppointments(apptsData)
  }

  async function handleBook(e: React.FormEvent) {
    e.preventDefault()
    const horse = horses.find(h => h.id === selectedHorseId)
    if (!horse) return alert('Please select a horse')

    // Count existing bookings at the same barn on this date
    const sameDaySameBarnCount = appointments.filter(
      a => a.appointment_date === bookingDate && a.barn_id === horse.barn_id
    ).length + 1 // including this new one

    const { travelFee, reason } = calculateTravelFee({
      distanceKm: Number(distanceKm),
      horsesBookedAtSameBarnSameDay: sameDaySameBarnCount
    })

    await supabase.from('appointments').insert([{
      appointment_date: bookingDate,
      horse_id: horse.id,
      barn_id: horse.barn_id,
      distance_from_base_km: Number(distanceKm),
      travel_fee: travelFee,
      status: 'Confirmed'
    }])

    alert(`Booking Confirmed! Travel Fee: $${travelFee.toFixed(2)} (${reason})`)
    setBookingDate('')
    loadData()
  }

  return (
    <main className="min-h-screen bg-slate-100 p-4 md:p-10 text-slate-800">
      <div className="max-w-5xl mx-auto space-y-8">
        
        {/* Navigation */}
        <div className="flex justify-between items-center bg-white p-4 rounded-2xl shadow-sm border border-slate-200">
          <Link href="/" className="text-emerald-700 font-bold hover:underline">← Back to Treatment Feed</Link>
          <span className="text-xs bg-emerald-100 text-emerald-800 font-semibold px-3 py-1 rounded-full">
            Smart Route Dispatcher
          </span>
        </div>

        {/* Schedule & Booking Form */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
          
          <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
            <h2 className="text-lg font-bold mb-4">Book Route Appointment</h2>
            <form onSubmit={handleBook} className="space-y-4">
              
              <div>
                <label className="block text-xs font-semibold text-slate-500 mb-1">Select Horse</label>
                <select 
                  value={selectedHorseId} onChange={e => setSelectedHorseId(e.target.value)}
                  className="w-full p-3 border rounded-xl text-sm focus:ring-2 focus:ring-emerald-500 outline-none bg-white" required
                >
                  <option value="">Choose Horse...</option>
                  {horses.map(h => (
                    <option key={h.id} value={h.id}>
                      {h.name} — {h.barns?.name || 'Private Barn'} ({h.owner_name})
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-500 mb-1">Appointment Date</label>
                <input 
                  type="date" value={bookingDate} onChange={e => setBookingDate(e.target.value)}
                  className="w-full p-3 border rounded-xl text-sm focus:ring-2 focus:ring-emerald-500 outline-none" required 
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-500 mb-1">Estimated Distance from Base (km)</label>
                <input 
                  type="number" value={distanceKm} onChange={e => setDistanceKm(Number(e.target.value))}
                  className="w-full p-3 border rounded-xl text-sm focus:ring-2 focus:ring-emerald-500 outline-none" required 
                />
                <p className="text-xs text-slate-400 mt-1">First 30km free. $0.73/km applied thereafter (auto-waived for 3+ horses at same barn).</p>
              </div>

              <button type="submit" className="w-full bg-emerald-700 text-white p-3 rounded-xl font-semibold text-sm hover:bg-emerald-800 transition">
                Confirm Appointment & Dispatch Route
              </button>
            </form>
          </div>

          {/* Regional Corridor Schedule */}
          <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-200 space-y-4">
            <h2 className="text-lg font-bold">Designated Route Corridors</h2>
            <div className="space-y-2">
              {zones.map(z => (
                <div key={z.id} className="p-3 bg-slate-50 border rounded-xl flex justify-between items-center text-sm">
                  <span className="font-semibold text-slate-700">{z.day_of_week}</span>
                  <span className="text-slate-500 text-xs bg-white px-2 py-1 rounded border">{z.zone_name}</span>
                </div>
              ))}
            </div>
          </div>

        </div>

        {/* Confirmed Schedule Table */}
        <div className="bg-white p-6 rounded-2xl shadow-sm border border-slate-200">
          <h2 className="text-lg font-bold mb-4">Upcoming Route Dispatches</h2>
          <div className="divide-y divide-slate-100">
            {appointments.map(a => (
              <div key={a.id} className="py-3 flex justify-between items-center text-sm">
                <div>
                  <span className="font-bold text-slate-900">{a.horses?.name}</span>
                  <span className="text-xs text-slate-500 ml-2">({a.horses?.barns?.name})</span>
                  <div className="text-xs text-slate-400">{a.appointment_date}</div>
                </div>
                <div className="text-right">
                  <span className="text-xs font-semibold px-2 py-1 rounded bg-slate-100">
                    Travel Fee: ${Number(a.travel_fee).toFixed(2)} CAD
                  </span>
                </div>
              </div>
            ))}
            {appointments.length === 0 && <p className="text-slate-400 text-sm py-4">No appointments scheduled.</p>}
          </div>
        </div>

      </div>
    </main>
  )
}