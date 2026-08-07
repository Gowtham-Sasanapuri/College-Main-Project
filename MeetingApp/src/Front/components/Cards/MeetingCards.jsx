import React, { useState } from 'react'
import styles from "./Cards.module.css"
import user from "./assets/two-user-svgrepo-com.svg"
import cam from "./assets/video-svgrepo-com.svg"
import CreateCard from './Sub_Cards/create/CreateCard'
import JoinMeet from './Sub_Cards/Join/JoinMeet'

const MeetingCards = () => {
    let [create,setCreate] = useState(false)
    let [join,setJoin] = useState(false)
    return (
        <>
        {
            !create && !join && (
        <div className={styles.Container}>
            <div className={styles.CreateMeeting + " " + styles.Card}>
                <div className={styles.ImgContainer}>
                    <img className={styles.Cam} src={cam} alt="Camer Image" />
                </div>
                <div className={styles.CardInfo}>
                    <p>Create Meeting</p>
                </div>
                <div className={styles.CardSubContentContainer}>
                    <p>Start a new meeting and share the link with others.</p>
                </div>
                <div className={styles.MeetingBtn}>
                    <button onClick={() => {
                        setCreate(true)
                        setJoin(false)
                    }}>Create Meeting</button>
                </div>
            </div>
            <div className={styles.JoinMeeting + " " + styles.Card}>
                <div className={styles.ImgContainer}>
                    <img className={styles.Cam} src={user} alt="Camer Image" />
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
                    }}>Join Meeting</button>
                </div>
            </div>
        </div>
            )
        }
        {
            create && !join && (
                <CreateCard Create = {setCreate}></CreateCard>
            )
        }
        {
            !create && join && (
                <JoinMeet Join = {setJoin}></JoinMeet>
            )
        }
        </>
    )
}

export default MeetingCards
