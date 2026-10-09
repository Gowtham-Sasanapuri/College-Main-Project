import React, { useState } from 'react'
import styles from "./Cards.module.css"
import user from "./assets/two-user-svgrepo-com.svg"
import cam from "./assets/video-svgrepo-com.svg"
import CreateCard from './Sub_Cards/create/CreateCard'
import CreateRoomCard from './Sub_Cards/create/CreateRoomCard'
import JoinMeet from './Sub_Cards/Join/JoinMeet'

const MeetingCards = () => {
    let [create, setCreate] = useState(false)
    let [createRoom, setCreateRoom] = useState(false)
    let [join, setJoin] = useState(false)
    return (
        <>
            {
                !create && !createRoom && !join && (
                    <div className={styles.Container}>
                        {/* 1. Create Video Meeting (Existing) */}
                        <div className={styles.CreateMeeting + " " + styles.Card}>
                            <div className={styles.ImgContainer}>
                                <img className={styles.Cam} src={cam} alt="Camera Image" />
                            </div>
                            <div className={styles.CardInfo}>
                                <p>Create Video Meeting</p>
                            </div>
                            <div className={styles.CardSubContentContainer}>
                                <p>Start a new WebRTC video meeting and share the link.</p>
                            </div>
                            <div className={styles.MeetingBtn}>
                                <button onClick={() => {
                                    setCreate(true)
                                    setCreateRoom(false)
                                    setJoin(false)
                                }}>Create Video Meeting</button>
                            </div>
                        </div>

                        {/* 2. Create Room Meeting (NEW) */}
                        <div className={styles.CreateMeeting + " " + styles.Card}>
                            <div className={styles.ImgContainer}>
                                <img className={styles.Cam} src={cam} alt="Mic Image" />
                            </div>
                            <div className={styles.CardInfo}>
                                <p>Create Room Meeting</p>
                            </div>
                            <div className={styles.CardSubContentContainer}>
                                <p>Place a central device in the room to record & diarize in-person speakers.</p>
                            </div>
                            <div className={styles.MeetingBtn}>
                                <button onClick={() => {
                                    setCreateRoom(true)
                                    setCreate(false)
                                    setJoin(false)
                                }}>Create Room Meeting</button>
                            </div>
                        </div>

                        {/* 3. Join Meeting (Existing) */}
                        <div className={styles.JoinMeeting + " " + styles.Card}>
                            <div className={styles.ImgContainer}>
                                <img className={styles.Cam} src={user} alt="Camera Image" />
                            </div>
                            <div className={styles.CardInfo}>
                                <p>Join Meeting</p>
                            </div>
                            <div className={styles.CardSubContentContainer}>
                                <p>Enter meeting Link to enter into existing meeting</p>
                            </div>
                            <div className={styles.MeetingBtn}>
                                <button onClick={() => {
                                    setJoin(true)
                                    setCreate(false)
                                    setCreateRoom(false)
                                }}>Join Meeting</button>
                            </div>
                        </div>
                    </div>
                )
            }
            {
                create && !createRoom && !join && (
                    <CreateCard Create={setCreate}></CreateCard>
                )
            }
            {
                createRoom && !create && !join && (
                    <CreateRoomCard Create={setCreateRoom}></CreateRoomCard>
                )
            }
            {
                !create && !createRoom && join && (
                    <JoinMeet Join={setJoin}></JoinMeet>
                )
            }
        </>
    )
}

export default MeetingCards
