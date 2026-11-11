import { useState } from 'react'
import { Route, BrowserRouter as Router, Routes } from "react-router-dom"
import Enter from './Front/Enter'
import Meeting from './MeetingPage/Meeting'
import RoomMeeting from './MeetingPage/RoomMeeting'
import MeetingSummaryMoM from './MeetingPage/MeetingSummaryMoM'
import { ThemeProvider } from './utils/ThemeContext'


function App() {
  return (
    <ThemeProvider>
      <Router>
        <Routes>
          <Route path='/' element={<Enter />} />
          <Route path="/Meeting/:id" element={<Meeting />} />
          <Route path="/RoomMeeting/:id" element={<RoomMeeting />} />
          <Route path="/MeetingSummary/:id" element={<MeetingSummaryMoM />} />
        </Routes>
      </Router>
    </ThemeProvider>
  )
}

export default App
