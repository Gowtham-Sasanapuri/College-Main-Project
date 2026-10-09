import { useState } from 'react'
import { Route, BrowserRouter as Router, Routes } from "react-router-dom"
import Enter from './Front/Enter'
import Meeting from './MeetingPage/Meeting'
import RoomMeeting from './MeetingPage/RoomMeeting'


function App() {


  return (
    <>
      <Router>
        <Routes>
          <Route path='/' element={<Enter></Enter>}></Route>
          <Route path="/Meeting/:id" element={<Meeting></Meeting>}></Route>
          <Route path="/RoomMeeting/:id" element={<RoomMeeting></RoomMeeting>}></Route>
        </Routes>
      </Router>
    </>
  )
}

export default App
